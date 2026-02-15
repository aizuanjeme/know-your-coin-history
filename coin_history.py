"""
Core logic for Know Your Coin History.

Features:
- Recursive transaction history tracing
- Script type identification (P2PKH, P2WPKH, P2TR, etc.)
- Wallet fingerprinting heuristics
- BIP-329 label management
- Graph data for the visualizer
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from bitcoin_rpc import BitcoinRPC


# ---------------------------------------------------------------------------
# Script type helpers
# ---------------------------------------------------------------------------

def identify_script_type(script_hex: str) -> str:
    """Identify the script type from a scriptPubKey hex string."""
    if not script_hex:
        return "unknown"
    
    # Check common script patterns
    if script_hex.startswith("76a914") and script_hex.endswith("88ac"):
        return "P2PKH"
    if script_hex.startswith("a914") and script_hex.endswith("87"):
        return "P2SH"
    if script_hex.startswith("0014") and len(script_hex) == 44:
        return "P2WPKH"
    if script_hex.startswith("0020") and len(script_hex) == 68:
        return "P2WSH"
    if script_hex.startswith("5120") and len(script_hex) == 68:
        return "P2TR"
    if script_hex.startswith("5121"):
        return "P2TR (script-path)"
    if script_hex.startswith("6a"):
        return "OP_RETURN"
    
    return "non-standard"


def address_from_spk(spk: dict) -> str:
    """Extract an address from a scriptPubKey dict (Core ≥ 22.0 uses 'address')."""
    if "address" in spk:
        return spk["address"]
    if "addresses" in spk and spk["addresses"]:
        return spk["addresses"][0]
    return spk.get("type", "unknown")


def estimated_input_vsize(script_type: str) -> int:
    """Estimate the vsize needed to spend an input of this type."""
    sizes = {
        "P2PKH": 148,
        "P2SH": 91,       # assumes P2SH-P2WPKH
        "P2WPKH": 68,
        "P2WSH": 104,
        "P2TR": 58,
    }
    return sizes.get(script_type, 68)


# ---------------------------------------------------------------------------
# Wallet fingerprinting
# ---------------------------------------------------------------------------

def detect_fingerprints(tx: dict) -> List[str]:
    """
    Analyze a transaction for wallet fingerprints.
    
    Returns a list of observations about locktime, version, sequence,
    output types, round amounts, etc.
    """
    hints: List[str] = []

    # Locktime analysis
    lt = tx.get("locktime", 0)
    if lt == 0:
        hints.append("locktime=0 — possible hardware wallet or older software")
    elif lt > 500_000_000:
        hints.append(f"locktime={lt} (UNIX timestamp-based)")
    else:
        hints.append(f"locktime={lt} (block-height anti-fee-sniping)")

    # --- version --------------------------------------------------
    ver = tx.get("version", 1)
    if ver == 1:
        hints.append("version=1 — legacy transaction format")
    elif ver == 2:
        hints.append("version=2 — enables BIP-68 relative lock-time")
    elif ver == 3:
        hints.append("version=3 — may indicate TRUC / v3 policy usage")
    else:
        hints.append(f"version={ver}")

    # --- nSequence values -----------------------------------------
    seqs: Set[int] = set()
    for vin in tx.get("vin", []):
        if "sequence" in vin:
            seqs.add(vin["sequence"])
    if seqs:
        for s in sorted(seqs):
            if s == 0xFFFFFFFF:
                hints.append("nSequence=0xFFFFFFFF — RBF disabled")
            elif s == 0xFFFFFFFD:
                hints.append("nSequence=0xFFFFFFFD — RBF signal (BIP-125)")
            elif s == 0xFFFFFFFE:
                hints.append("nSequence=0xFFFFFFFE — locktime enabled, no RBF")
            else:
                hints.append(f"nSequence=0x{s:08X}")

    # --- output-type mixing ---------------------------------------
    out_types: List[str] = []
    for vout in tx.get("vout", []):
        spk = vout.get("scriptPubKey", {})
        out_types.append(identify_script_type(spk.get("hex", "")))

    unique = set(out_types)
    if len(unique) > 1:
        hints.append(f"Mixed output types {unique} — potential change-output leak")

    # --- round-number heuristic -----------------------------------
    for vout in tx.get("vout", []):
        val_sats = int(Decimal(str(vout["value"])) * 100_000_000)
        if val_sats > 0 and val_sats % 100_000 == 0:
            hints.append(
                f"Output #{vout['n']} has round value {vout['value']} BTC"
                " — likely a payment (not change)"
            )

    # Input/output count
    n_in = len(tx.get("vin", []))
    n_out = len(tx.get("vout", []))
    if n_out == 1:
        hints.append("Single output — sweep or consolidation")
    if n_out == 2:
        hints.append("Two outputs — typical spend (payment + change)")
    if n_in > 5:
        hints.append(f"{n_in} inputs — UTXO consolidation or high-volume wallet")

    return hints


# ---------------------------------------------------------------------------
# BIP-329 Label Manager
# ---------------------------------------------------------------------------

class LabelManager:
    """
    Manage BIP-329 wallet labels (JSONL format).
    
    BIP-329 defines a standard format for wallet label import/export.
    Spec: https://github.com/bitcoin/bips/blob/master/bip-0329.mediawiki
    
    Required fields:
        - type: One of tx, addr, pubkey, input, output, xpub
        - ref: Reference to the item (txid, address, pubkey hex, txid:index, xpub)
    
    Optional fields (all types):
        - label: The label text (max 255 chars recommended)
        - origin: Key origin descriptor e.g. "wpkh([d34db33f/84'/0'/0'])"
    
    Optional fields (output only):
        - spendable: true/false - whether output should be spendable
    
    Additional optional fields for transactions:
        - height: Block height (omit if < 6 confirmations)
        - time: ISO-8601 timestamp of the block
        - fee: Satoshis paid to miner
        - value: Signed satoshis in/out of wallet
        - rate: Exchange rate dict e.g. {"USD": 105620.00}
    
    Additional optional fields for inputs/outputs:
        - value: Satoshis (nValue)
        - fmv: Fair market value dict e.g. {"USD": 1233.45}
        - keypath: Descriptor path extension e.g. "/1/123"
        - height, time: Same as transactions
    
    Additional optional fields for addresses:
        - heights: List of block heights with activity
    """

    VALID_TYPES = {"tx", "addr", "pubkey", "input", "output", "xpub"}

    def __init__(self) -> None:
        self.labels: Dict[str, Dict[str, Any]] = {}  # ref -> {type, ref, label, ...}

    # ---------- CRUD ------------
    def add(
        self,
        label_type: str,
        ref: str,
        label: str = "",
        *,
        origin: str = "",
        spendable: Optional[bool] = None,
        height: Optional[int] = None,
        time: str = "",
        fee: Optional[int] = None,
        value: Optional[int] = None,
        rate: Optional[Dict[str, float]] = None,
        fmv: Optional[Dict[str, float]] = None,
        keypath: str = "",
        heights: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """
        Add or update a BIP-329 label entry.
        
        Args:
            label_type: One of tx, addr, pubkey, input, output, xpub
            ref: Reference string (txid, address, etc.)
            label: Label text
            origin: Key origin descriptor
            spendable: Whether output is spendable (output type only)
            height: Block height (tx, input, output)
            time: ISO-8601 timestamp
            fee: Transaction fee in satoshis (tx only)
            value: Satoshi amount
            rate: Exchange rate dict (tx only)
            fmv: Fair market value dict (input, output)
            keypath: BIP32 path extension (addr, input, output)
            heights: List of activity heights (addr only)
        
        Returns:
            The created/updated entry dict
        """
        if label_type not in self.VALID_TYPES:
            raise ValueError(f"Invalid type '{label_type}'. Must be one of: {self.VALID_TYPES}")
        
        entry: Dict[str, Any] = {"type": label_type, "ref": ref}
        
        # Required/common optional fields
        if label:
            entry["label"] = label[:255]  # BIP-329 recommends max 255 chars
        if origin:
            entry["origin"] = origin
        
        # Output-only field
        if label_type == "output" and spendable is not None:
            entry["spendable"] = spendable
        
        # Transaction fields
        if label_type == "tx":
            if height is not None and height > 0:
                entry["height"] = height
            if time:
                entry["time"] = time
            if fee is not None:
                entry["fee"] = fee
            if value is not None:
                entry["value"] = value
            if rate:
                entry["rate"] = rate
        
        # Input/Output fields
        if label_type in ("input", "output"):
            if value is not None:
                entry["value"] = value
            if fmv:
                entry["fmv"] = fmv
            if keypath:
                entry["keypath"] = keypath
            if height is not None and height > 0:
                entry["height"] = height
            if time:
                entry["time"] = time
        
        # Address fields
        if label_type == "addr":
            if keypath:
                entry["keypath"] = keypath
            if heights is not None:
                entry["heights"] = heights
        
        self.labels[ref] = entry
        return entry

    # Backwards compatibility alias
    def set_label(
        self, label_type: str, ref: str, label: str, origin: str = ""
    ) -> None:
        """Backwards compatible method. Use add() for full BIP-329 support."""
        self.add(label_type, ref, label, origin=origin)

    def get(self, ref: str) -> Optional[Dict[str, Any]]:
        """Get the full label entry for a reference."""
        return self.labels.get(ref)

    def get_label(self, ref: str) -> str:
        """Get just the label text for a reference."""
        return self.labels.get(ref, {}).get("label", "")

    def delete(self, ref: str) -> bool:
        """Delete a label entry. Returns True if deleted, False if not found."""
        if ref in self.labels:
            del self.labels[ref]
            return True
        return False

    # Backwards compatibility alias
    def delete_label(self, ref: str) -> None:
        """Backwards compatible method. Use delete() instead."""
        self.delete(ref)

    def all_labels(self) -> List[Dict[str, Any]]:
        """Return all label entries as a list."""
        return list(self.labels.values())

    def by_type(self, label_type: str) -> List[Dict[str, Any]]:
        """Return all labels of a specific type."""
        return [e for e in self.labels.values() if e.get("type") == label_type]

    def frozen_outputs(self) -> List[str]:
        """Return list of output refs marked as non-spendable (frozen)."""
        return [
            e["ref"] for e in self.labels.values()
            if e.get("type") == "output" and e.get("spendable") is False
        ]

    # ---------- Import / Export ---------
    def export_bip329(self, filepath: str | Path) -> int:
        """
        Export labels to a BIP-329 JSONL file.
        
        Returns:
            Number of labels exported
        """
        count = 0
        with open(filepath, "w", encoding="utf-8") as fh:
            for entry in self.labels.values():
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
                count += 1
        return count

    def export_bip329_string(self) -> str:
        """Export labels to a BIP-329 JSONL string."""
        lines = [json.dumps(entry, ensure_ascii=False) for entry in self.labels.values()]
        return "\n".join(lines)

    def import_bip329(self, filepath: str | Path) -> int:
        """
        Import labels from a BIP-329 JSONL file.
        
        Returns:
            Number of labels imported
        """
        count = 0
        with open(filepath, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if self._validate_entry(entry):
                        self.labels[entry["ref"]] = entry
                        count += 1
                except json.JSONDecodeError:
                    continue  # Skip malformed lines per BIP-329
        return count

    def import_bip329_string(self, data: str) -> int:
        """
        Import labels from a BIP-329 JSONL string.
        
        Returns:
            Number of labels imported
        """
        count = 0
        for line in data.split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if self._validate_entry(entry):
                    self.labels[entry["ref"]] = entry
                    count += 1
            except json.JSONDecodeError:
                continue
        return count

    def _validate_entry(self, entry: dict) -> bool:
        """Validate a BIP-329 entry has required fields."""
        if not isinstance(entry, dict):
            return False
        if "type" not in entry or "ref" not in entry:
            return False
        if entry["type"] not in self.VALID_TYPES:
            return False
        # spendable only valid for output type
        if "spendable" in entry and entry["type"] != "output":
            return False
        return True

    def clear(self) -> None:
        """Clear all labels."""
        self.labels.clear()


# ---------------------------------------------------------------------------
# Transaction History Tracer
# ---------------------------------------------------------------------------

class CoinHistory:
    """
    Recursively traces transaction history using a local Bitcoin Core node.
    
    Builds a graph of transactions, inputs, and outputs that can be
    visualized in the web UI.
    """

    def __init__(self, rpc: BitcoinRPC):
        self.rpc = rpc
        self.labels = LabelManager()
        self._tx_cache: Dict[str, dict] = {}
        
        # Graph data for visualization
        self.nodes: Dict[str, dict] = {}  # node_id -> {label, type, ...}
        self.edges: List[dict] = []       # [{from, to, label, ...}]

    def _get_tx(self, txid: str) -> Optional[dict]:
        """Fetch a transaction, using cache if available."""
        if txid in self._tx_cache:
            return self._tx_cache[txid]
        try:
            tx = self.rpc.getrawtransaction(txid, verbose=True)
            self._tx_cache[txid] = tx
            return tx
        except Exception:
            return None

    # ---------- tracing -------------------

    def trace(
        self,
        txid: str,
        max_depth: int = 5,
        *,
        _depth: int = 0,
        _visited: Optional[Set[str]] = None,
    ) -> None:
        """Recursively trace the history of *txid* up to *max_depth* hops."""
        if _visited is None:
            _visited = set()
        if txid in _visited or _depth > max_depth:
            return
        _visited.add(txid)

        tx = self._get_tx(txid)
        if tx is None:
            return

        # ---- build graph node for this tx ----
        total_out = sum(Decimal(str(v["value"])) for v in tx.get("vout", []))
        self.nodes[txid] = {
            "id": txid,
            "label": f"{txid[:8]}…\n{total_out} BTC",
            "title": txid,
            "type": "tx",
            "depth": _depth,
            "group": f"depth-{_depth}",
        }

        # ---- outputs → outpoint nodes ----
        for vout in tx.get("vout", []):
            spk = vout.get("scriptPubKey", {})
            addr = address_from_spk(spk)
            stype = identify_script_type(spk.get("hex", ""))
            op_id = f"{txid}:{vout['n']}"
            self.nodes[op_id] = {
                "id": op_id,
                "label": f"{vout['value']} BTC",
                "title": f"{op_id}\n{addr}\n{stype}",
                "type": "utxo",
                "address": addr,
                "script_type": stype,
                "value": str(vout["value"]),
                "group": stype,
            }
            self.edges.append({
                "from": txid,
                "to": op_id,
                "label": f"{vout['value']}",
                "arrows": "to",
            })

        # ---- inputs (recurse) ----
        for vin in tx.get("vin", []):
            if "coinbase" in vin:
                cb_id = f"coinbase:{txid}"
                self.nodes[cb_id] = {
                    "id": cb_id,
                    "label": "Coinbase",
                    "title": "Block reward",
                    "type": "coinbase",
                    "group": "coinbase",
                }
                self.edges.append({
                    "from": cb_id,
                    "to": txid,
                    "label": "coinbase",
                    "arrows": "to",
                })
                continue

            prev_txid = vin["txid"]
            prev_vout = vin["vout"]
            op_id = f"{prev_txid}:{prev_vout}"

            # Ensure the outpoint node exists
            if op_id not in self.nodes:
                prev_tx = self._get_tx(prev_txid)
                if prev_tx and prev_vout < len(prev_tx["vout"]):
                    v = prev_tx["vout"][prev_vout]
                    spk = v.get("scriptPubKey", {})
                    addr = address_from_spk(spk)
                    stype = identify_script_type(spk.get("hex", ""))
                    self.nodes[op_id] = {
                        "id": op_id,
                        "label": f"{v['value']} BTC",
                        "title": f"{op_id}\n{addr}\n{stype}",
                        "type": "utxo",
                        "address": addr,
                        "script_type": stype,
                        "value": str(v["value"]),
                        "group": stype,
                    }

            # Edge: outpoint → this tx
            self.edges.append({
                "from": op_id,
                "to": txid,
                "label": "spent",
                "arrows": "to",
                "dashes": True,
            })

            # Recurse into the parent transaction
            self.trace(prev_txid, max_depth, _depth=_depth + 1, _visited=_visited)

    # ---------- summaries -----------------

    def tx_summary(self, txid: str) -> Optional[dict]:
        """Return a rich summary of *txid* including fingerprinting info."""
        tx = self._get_tx(txid)
        if tx is None:
            return None

        total_in = Decimal(0)
        inputs: List[dict] = []
        for vin in tx.get("vin", []):
            if "coinbase" in vin:
                inputs.append({
                    "type": "coinbase",
                    "label": self.labels.get_label(f"coinbase:{txid}"),
                })
                continue
            prev_tx = self._get_tx(vin["txid"])
            if prev_tx and vin["vout"] < len(prev_tx["vout"]):
                v = prev_tx["vout"][vin["vout"]]
                val = Decimal(str(v["value"]))
                total_in += val
                spk = v.get("scriptPubKey", {})
                outpoint = f"{vin['txid']}:{vin['vout']}"
                inputs.append({
                    "txid": vin["txid"],
                    "vout": vin["vout"],
                    "value": str(val),
                    "address": address_from_spk(spk),
                    "script_type": identify_script_type(spk.get("hex", "")),
                    "input_vsize": estimated_input_vsize(
                        identify_script_type(spk.get("hex", ""))
                    ),
                    "label": self.labels.get_label(outpoint),
                })
            else:
                inputs.append({
                    "txid": vin["txid"],
                    "vout": vin["vout"],
                    "value": "unknown",
                })

        total_out = Decimal(0)
        outputs: List[dict] = []
        for vout in tx.get("vout", []):
            val = Decimal(str(vout["value"]))
            total_out += val
            spk = vout.get("scriptPubKey", {})
            outpoint = f"{txid}:{vout['n']}"
            outputs.append({
                "n": vout["n"],
                "value": str(val),
                "address": address_from_spk(spk),
                "script_type": identify_script_type(spk.get("hex", "")),
                "label": self.labels.get_label(outpoint),
            })

        fee = total_in - total_out if total_in > 0 else Decimal(0)
        fee_rate = (
            float(fee * 100_000_000) / tx["vsize"]
            if total_in > 0 and tx.get("vsize")
            else None
        )

        return {
            "txid": txid,
            "size": tx.get("size"),
            "vsize": tx.get("vsize"),
            "weight": tx.get("weight"),
            "version": tx.get("version"),
            "locktime": tx.get("locktime"),
            "confirmations": tx.get("confirmations", 0),
            "blockhash": tx.get("blockhash", ""),
            "inputs": inputs,
            "outputs": outputs,
            "total_in": str(total_in),
            "total_out": str(total_out),
            "fee_btc": str(fee),
            "fee_rate_sat_vb": round(fee_rate, 2) if fee_rate is not None else None,
            "fingerprints": detect_fingerprints(tx),
            "label": self.labels.get_label(txid),
        }

    # ---------- wallet helpers ---------------

    def list_wallet_coins(self) -> List[dict]:
        """
        Return the wallet's UTXOs enriched with spendability information.
        
        Bitcoin Core's listunspent returns:
        - spendable: We have the private key to spend
        - solvable: We know how to construct a valid scriptSig/witness
        - safe: Output is safe to spend (confirmed or from ourselves)
        
        We also check:
        - BIP-329 frozen status (user manually froze the output)
        - Timelock status (CLTV/CSV restrictions)
        """
        utxos = self.rpc.listunspent(minconf=0)  # Include unconfirmed
        current_height = self.rpc.getblockcount()
        
        for u in utxos:
            op = f"{u['txid']}:{u['vout']}"
            
            # Script type identification
            u["script_type"] = identify_script_type(u.get("scriptPubKey", ""))
            
            # Label from BIP-329 store
            u["label"] = self.labels.get_label(op)
            
            # Spendability sources from Bitcoin Core
            # These are already provided by listunspent
            core_spendable = u.get("spendable", False)
            core_solvable = u.get("solvable", False)
            core_safe = u.get("safe", True)
            
            # Check if user froze this output via BIP-329
            label_entry = self.labels.get(op)
            user_frozen = False
            if label_entry and label_entry.get("spendable") is False:
                user_frozen = True
            
            # Check for timelocks by examining the spending script
            # For standard outputs, check if there's a locktimed spending condition
            timelock_info = self._check_timelock(u, current_height)
            
            # Final spendability determination
            u["spendability"] = {
                "can_spend": core_spendable and core_safe and not user_frozen and timelock_info["unlocked"],
                "has_key": core_spendable,
                "solvable": core_solvable,
                "safe": core_safe,
                "frozen": user_frozen,
                "timelock": timelock_info,
                "reason": self._spendability_reason(
                    core_spendable, core_solvable, core_safe, 
                    user_frozen, timelock_info
                )
            }
            
        return utxos

    def _check_timelock(self, utxo: dict, current_height: int) -> dict:
        """
        Check if a UTXO has timelock restrictions.
        
        Returns dict with:
        - unlocked: Whether the timelock has passed
        - type: None, 'cltv', or 'csv'
        - value: The timelock value (height or time)
        - blocks_remaining: How many blocks until unlocked (if applicable)
        """
        # For standard P2PKH/P2WPKH/P2TR, there are no script-level timelocks
        # Timelocks are typically in P2SH/P2WSH scripts
        
        script_type = utxo.get("script_type", "")
        
        # Standard single-sig outputs don't have script timelocks
        if script_type in ("P2PKH", "P2WPKH", "P2TR"):
            return {"unlocked": True, "type": None, "value": None, "blocks_remaining": 0}
        
        # For P2SH/P2WSH, we'd need to decode the redeemScript/witnessScript
        # to detect OP_CLTV or OP_CSV - this requires the script which isn't
        # always available from listunspent
        
        # Check if we have redeemScript to analyze
        redeem_script = utxo.get("redeemScript", "")
        witness_script = utxo.get("witnessScript", "")
        script_to_check = witness_script or redeem_script
        
        if script_to_check:
            return self._parse_timelock_from_script(script_to_check, current_height, utxo)
        
        # Can't determine - assume unlocked
        return {"unlocked": True, "type": None, "value": None, "blocks_remaining": 0}

    def _parse_timelock_from_script(self, script_hex: str, current_height: int, utxo: dict) -> dict:
        """Parse script for CLTV/CSV opcodes."""
        # OP_CHECKLOCKTIMEVERIFY = 0xb1
        # OP_CHECKSEQUENCEVERIFY = 0xb2
        
        if "b1" in script_hex.lower():  # Contains OP_CLTV
            # Would need full script parsing to extract the value
            # For now, mark as potentially timelocked
            return {
                "unlocked": True,  # Assume unlocked without full parsing
                "type": "cltv",
                "value": "unknown",
                "blocks_remaining": 0,
                "note": "Script contains CLTV - may have time restrictions"
            }
        
        if "b2" in script_hex.lower():  # Contains OP_CSV
            return {
                "unlocked": True,
                "type": "csv", 
                "value": "unknown",
                "blocks_remaining": 0,
                "note": "Script contains CSV - may have relative time restrictions"
            }
        
        return {"unlocked": True, "type": None, "value": None, "blocks_remaining": 0}

    def _spendability_reason(
        self, 
        has_key: bool, 
        solvable: bool,
        safe: bool, 
        frozen: bool, 
        timelock: dict
    ) -> str:
        """Generate a human-readable reason for spendability status."""
        if not has_key:
            return "🔒 Watch-only - no private key"
        if not solvable:
            return "❓ Unknown script type - cannot create signature"
        if not safe:
            return "⚠️ Unsafe to spend - unconfirmed from others"
        if frozen:
            return "❄️ Frozen by user (BIP-329)"
        if not timelock["unlocked"]:
            remaining = timelock.get("blocks_remaining", "?")
            return f"⏰ Timelocked - {remaining} blocks remaining"
        return "✅ Spendable"

    # ---------- graph data for frontend ------

    def graph_data(self) -> dict:
        """Return nodes and edges ready for vis.js Network."""
        return {
            "nodes": list(self.nodes.values()),
            "edges": self.edges,
        }

    def reset_graph(self) -> None:
        self.nodes.clear()
        self.edges.clear()
        self._tx_cache.clear()
