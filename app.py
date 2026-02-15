#!/usr/bin/env python3
"""
Know Your Coin History — Flask web application.

A privacy-focused tool to explore and label the history of your Bitcoin UTXOs.
Runs against a local Bitcoin Core node with txindex enabled.

Usage:
    pip install -r requirements.txt
    bitcoind -datadir=$PWD/datadir/node0
    python app.py

Then open http://127.0.0.1:5000 in your browser.
"""

import json
import os
from decimal import Decimal
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from bitcoin_rpc import BitcoinRPC, RPCError
from coin_history import CoinHistory


# ---------------------------------------------------------------------------
# Configuration (override with environment variables if needed)
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
LABELS_FILE = BASE_DIR / "labels.jsonl"

# RPC connection settings - see docs/CREDENTIALS.md for details
RPC_URL = os.environ.get("RPC_URL", "http://127.0.0.1:18443")
RPC_USER = os.environ.get("RPC_USER", "admin")
RPC_PASS = os.environ.get("RPC_PASS", "history2026")
WALLET = os.environ.get("WALLET", "student")


# ---------------------------------------------------------------------------
# App initialization
# ---------------------------------------------------------------------------

app = Flask(__name__)

rpc = BitcoinRPC(url=RPC_URL, user=RPC_USER, password=RPC_PASS, wallet=WALLET)
history = CoinHistory(rpc)

# Load any existing labels from disk
if LABELS_FILE.exists():
    history.labels.import_bip329(LABELS_FILE)


def _persist_labels():
    """Write labels to disk. Called after any label change."""
    history.labels.export_bip329(LABELS_FILE)


# ---------------------------------------------------------------------------
# Web pages
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# API - Exploration endpoints
# ---------------------------------------------------------------------------

@app.route("/api/trace", methods=["POST"])
def api_trace():
    """Trace the history of a txid and return vis.js graph data."""
    data = request.get_json(force=True)
    txid = data.get("txid", "").strip()
    depth = min(int(data.get("depth", 5)), 20)  # cap at 20 levels deep
    reset = data.get("reset", True)

    if not txid:
        return jsonify({"error": "txid is required"}), 400

    try:
        if reset:
            history.reset_graph()
        history.trace(txid, max_depth=depth)
        return jsonify(history.graph_data())
    except RPCError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/tx/<txid>")
def api_tx_detail(txid: str):
    """Get detailed info about a single transaction."""
    try:
        summary = history.tx_summary(txid)
        if summary is None:
            return jsonify({"error": "Transaction not found"}), 404
        return jsonify(summary)
    except RPCError as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/api/utxos")
def api_utxos():
    """List all unspent outputs in the current wallet."""
    try:
        coins = history.list_wallet_coins()
        return jsonify(json.loads(json.dumps(coins, default=str)))
    except RPCError as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/api/balance")
def api_balance():
    try:
        return jsonify(rpc.getbalances())
    except RPCError as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/api/blockcount")
def api_blockcount():
    try:
        return jsonify({"blockcount": rpc.getblockcount()})
    except RPCError as exc:
        return jsonify({"error": str(exc)}), 502


# ---------------------------------------------------------------------------
# API - Label management (BIP-329)
# ---------------------------------------------------------------------------

@app.route("/api/labels", methods=["GET"])
def api_labels_list():
    """Get all labels."""
    return jsonify(history.labels.all_labels())


@app.route("/api/labels", methods=["POST"])
def api_labels_set():
    """
    Create or update a BIP-329 label.
    
    If a label with the same ref already exists, it gets updated.
    
    Request body fields (only type and ref are required):
        type: tx | addr | pubkey | input | output | xpub
        ref: txid, address, pubkey hex, txid:vout, or xpub
        label: Label text (max 255 chars)
        origin: Key origin descriptor, e.g. wpkh([fingerprint/path])
        spendable: true/false (output type only)
        height: Block height
        time: ISO-8601 timestamp
        fee: Satoshis (tx only)
        value: Satoshi amount
        rate: Exchange rate dict (tx only)
        fmv: Fair market value dict (input/output only)
        keypath: BIP32 path extension
        heights: List of block heights (addr only)
    """
    data = request.get_json(force=True)
    ltype = data.get("type", "tx")
    ref = data.get("ref", "").strip()

    if not ref:
        return jsonify({"error": "ref is required"}), 400

    existing = history.labels.get(ref)
    is_update = existing is not None

    try:
        entry = history.labels.add(
            label_type=ltype,
            ref=ref,
            label=data.get("label", ""),
            origin=data.get("origin", ""),
            spendable=data.get("spendable"),
            height=data.get("height"),
            time=data.get("time", ""),
            fee=data.get("fee"),
            value=data.get("value"),
            rate=data.get("rate"),
            fmv=data.get("fmv"),
            keypath=data.get("keypath", ""),
            heights=data.get("heights"),
        )
        _persist_labels()
        return jsonify({
            "ok": True, 
            "entry": entry,
            "action": "updated" if is_update else "created",
            "message": f"Label {'updated' if is_update else 'created'} for {ref[:20]}..."
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/labels/<path:ref>", methods=["DELETE"])
def api_labels_delete(ref: str):
    deleted = history.labels.delete(ref)
    if deleted:
        _persist_labels()
    return jsonify({"ok": True, "deleted": deleted})


@app.route("/api/labels/<path:ref>", methods=["GET"])
def api_label_get(ref: str):
    """Get a single label entry by reference."""
    entry = history.labels.get(ref)
    if entry is None:
        return jsonify({"error": "Label not found"}), 404
    return jsonify(entry)


@app.route("/api/labels/by-type/<label_type>", methods=["GET"])
def api_labels_by_type(label_type: str):
    """Get all labels of a specific type (tx, addr, pubkey, input, output, xpub)."""
    return jsonify(history.labels.by_type(label_type))


@app.route("/api/labels/frozen", methods=["GET"])
def api_frozen_outputs():
    """Get list of frozen (non-spendable) output refs."""
    return jsonify(history.labels.frozen_outputs())


@app.route("/api/labels/export", methods=["GET"])
def api_labels_export():
    """Download labels as a BIP-329 JSONL file."""
    content = history.labels.export_bip329_string()
    if content:
        content += "\n"
    return app.response_class(
        content,
        mimetype="application/jsonl",
        headers={"Content-Disposition": "attachment; filename=labels.jsonl"},
    )


@app.route("/api/labels/import", methods=["POST"])
def api_labels_import():
    """Import labels from an uploaded BIP-329 JSONL file."""
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "No file uploaded"}), 400

    content = f.stream.read().decode("utf-8")
    count = history.labels.import_bip329_string(content)
    _persist_labels()
    return jsonify({"imported": count})


# ---------------------------------------------------------------------------
# API - Wallet management
# ---------------------------------------------------------------------------

@app.route("/api/wallets")
def api_wallets():
    """List all loaded wallets."""
    try:
        return jsonify(rpc.listwallets())
    except RPCError as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/api/wallets/switch", methods=["POST"])
def api_wallets_switch():
    """Switch to a different wallet."""
    global rpc, history
    data = request.get_json(force=True)
    name = data.get("wallet", "").strip()
    if not name:
        return jsonify({"error": "wallet name required"}), 400
    
    rpc = BitcoinRPC(url=RPC_URL, user=RPC_USER, password=RPC_PASS, wallet=name)
    history = CoinHistory(rpc)
    if LABELS_FILE.exists():
        history.labels.import_bip329(LABELS_FILE)
    return jsonify({"ok": True, "wallet": name})


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("-" * 60)
    print("  Know Your Coin History")
    print(f"  RPC: {RPC_URL} (wallet: {WALLET})")
    print(f"  Labels: {LABELS_FILE}")
    print("  Open http://127.0.0.1:5000 in your browser")
    print("-" * 60)
    app.run(debug=True, host="127.0.0.1", port=5000)
