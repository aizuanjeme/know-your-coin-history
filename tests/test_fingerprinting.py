"""
Tests for wallet fingerprinting heuristics.

These detect transaction patterns that reveal wallet software,
spending behavior, and potential privacy leaks.

Run with: pytest tests/test_fingerprinting.py -v
"""

import pytest
from decimal import Decimal

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from coin_history import detect_fingerprints


def make_tx(
    version=2,
    locktime=0,
    vin=None,
    vout=None,
):
    """Factory for creating test transaction dicts."""
    return {
        "version": version,
        "locktime": locktime,
        "vin": vin or [{"sequence": 0xFFFFFFFD}],
        "vout": vout or [{"n": 0, "value": "1.0", "scriptPubKey": {"hex": "0014" + "0" * 40}}],
    }


class TestLocktimeFingerprinting:
    """Test locktime analysis for wallet fingerprints."""

    @pytest.mark.unit
    def test_locktime_zero(self):
        """locktime=0 suggests hardware wallet or older software."""
        tx = make_tx(locktime=0)
        hints = detect_fingerprints(tx)
        assert any("locktime=0" in h for h in hints)
        assert any("hardware wallet" in h.lower() or "older" in h.lower() for h in hints)

    @pytest.mark.unit
    def test_locktime_block_height(self):
        """locktime < 500M is a block height (anti-fee-sniping)."""
        tx = make_tx(locktime=800000)
        hints = detect_fingerprints(tx)
        assert any("800000" in h for h in hints)
        assert any("block-height" in h or "anti-fee-sniping" in h for h in hints)

    @pytest.mark.unit
    def test_locktime_unix_timestamp(self):
        """locktime >= 500M is a UNIX timestamp."""
        tx = make_tx(locktime=1700000000)  # Some future timestamp
        hints = detect_fingerprints(tx)
        assert any("1700000000" in h for h in hints)
        assert any("UNIX" in h or "timestamp" in h for h in hints)


class TestVersionFingerprinting:
    """Test transaction version analysis."""

    @pytest.mark.unit
    def test_version_1(self):
        """version=1 is legacy transaction format."""
        tx = make_tx(version=1)
        hints = detect_fingerprints(tx)
        assert any("version=1" in h for h in hints)
        assert any("legacy" in h.lower() for h in hints)

    @pytest.mark.unit
    def test_version_2(self):
        """version=2 enables BIP-68 relative lock-time."""
        tx = make_tx(version=2)
        hints = detect_fingerprints(tx)
        assert any("version=2" in h for h in hints)
        assert any("BIP-68" in h for h in hints)

    @pytest.mark.unit
    def test_version_3(self):
        """version=3 may indicate TRUC/v3 policy."""
        tx = make_tx(version=3)
        hints = detect_fingerprints(tx)
        assert any("version=3" in h for h in hints)


class TestSequenceFingerprinting:
    """Test nSequence analysis for RBF and other signals."""

    @pytest.mark.unit
    def test_sequence_max_no_rbf(self):
        """nSequence=0xFFFFFFFF disables RBF."""
        tx = make_tx(vin=[{"sequence": 0xFFFFFFFF}])
        hints = detect_fingerprints(tx)
        matching = [h for h in hints if "0xFFFFFFFF" in h]
        assert len(matching) > 0
        assert any("RBF disabled" in h for h in matching)

    @pytest.mark.unit
    def test_sequence_rbf_signal(self):
        """nSequence=0xFFFFFFFD signals RBF (BIP-125)."""
        tx = make_tx(vin=[{"sequence": 0xFFFFFFFD}])
        hints = detect_fingerprints(tx)
        matching = [h for h in hints if "0xFFFFFFFD" in h]
        assert len(matching) > 0
        assert any("RBF signal" in h or "BIP-125" in h for h in matching)

    @pytest.mark.unit
    def test_sequence_locktime_enabled(self):
        """nSequence=0xFFFFFFFE enables locktime but no RBF."""
        tx = make_tx(vin=[{"sequence": 0xFFFFFFFE}])
        hints = detect_fingerprints(tx)
        matching = [h for h in hints if "0xFFFFFFFE" in h]
        assert len(matching) > 0
        assert any("locktime enabled" in h.lower() for h in matching)

    @pytest.mark.unit
    def test_multiple_sequences(self):
        """Multiple inputs with different sequences."""
        tx = make_tx(vin=[
            {"sequence": 0xFFFFFFFD},
            {"sequence": 0xFFFFFFFE},
        ])
        hints = detect_fingerprints(tx)
        # Should report both sequences
        assert any("0xFFFFFFFD" in h for h in hints)
        assert any("0xFFFFFFFE" in h for h in hints)


class TestOutputTypeFingerprinting:
    """Test output type mixing detection."""

    @pytest.mark.unit
    def test_single_output_type(self):
        """All outputs same type - no mixing detected."""
        tx = make_tx(vout=[
            {"n": 0, "value": "1.0", "scriptPubKey": {"hex": "0014" + "0" * 40}},  # P2WPKH
            {"n": 1, "value": "0.5", "scriptPubKey": {"hex": "0014" + "1" * 40}},  # P2WPKH
        ])
        hints = detect_fingerprints(tx)
        # Should NOT mention "Mixed output types"
        assert not any("Mixed output types" in h for h in hints)

    @pytest.mark.unit
    def test_mixed_output_types(self):
        """Mixed output types may leak change output identity."""
        tx = make_tx(vout=[
            {"n": 0, "value": "1.0", "scriptPubKey": {"hex": "0014" + "0" * 40}},  # P2WPKH
            {"n": 1, "value": "0.5", "scriptPubKey": {"hex": "76a914" + "0" * 40 + "88ac"}},  # P2PKH
        ])
        hints = detect_fingerprints(tx)
        assert any("Mixed output types" in h for h in hints)
        assert any("change" in h.lower() for h in hints)

    @pytest.mark.unit
    def test_legacy_to_segwit_migration(self):
        """Common pattern: send to SegWit, change to legacy (or vice versa)."""
        tx = make_tx(vout=[
            {"n": 0, "value": "1.0", "scriptPubKey": {"hex": "5120" + "0" * 64}},  # P2TR (payment)
            {"n": 1, "value": "0.5", "scriptPubKey": {"hex": "0014" + "0" * 40}},  # P2WPKH (change)
        ])
        hints = detect_fingerprints(tx)
        assert any("Mixed" in h for h in hints)


class TestRoundAmountFingerprinting:
    """Test round amount (payment vs change) heuristics."""

    @pytest.mark.unit
    def test_round_btc_amount(self):
        """Round BTC amounts likely indicate payments."""
        tx = make_tx(vout=[
            {"n": 0, "value": "1.0", "scriptPubKey": {"hex": "0014" + "0" * 40}},
            {"n": 1, "value": "0.12345678", "scriptPubKey": {"hex": "0014" + "1" * 40}},
        ])
        hints = detect_fingerprints(tx)
        assert any("round value" in h.lower() and "1.0 BTC" in h for h in hints)
        assert any("payment" in h.lower() for h in hints)

    @pytest.mark.unit
    def test_round_mbtc_amount(self):
        """Round mBTC amounts (0.001, 0.01, etc.)."""
        tx = make_tx(vout=[
            {"n": 0, "value": "0.01", "scriptPubKey": {"hex": "0014" + "0" * 40}},  # 1 mBTC
            {"n": 1, "value": "0.00123456", "scriptPubKey": {"hex": "0014" + "1" * 40}},
        ])
        hints = detect_fingerprints(tx)
        assert any("round value" in h.lower() and "0.01 BTC" in h for h in hints)

    @pytest.mark.unit
    def test_no_round_amounts(self):
        """Weird amounts on all outputs - harder to identify change."""
        tx = make_tx(vout=[
            {"n": 0, "value": "0.12345678", "scriptPubKey": {"hex": "0014" + "0" * 40}},
            {"n": 1, "value": "0.87654321", "scriptPubKey": {"hex": "0014" + "1" * 40}},
        ])
        hints = detect_fingerprints(tx)
        # Should NOT flag round amounts
        assert not any("round value" in h.lower() for h in hints)


class TestInputOutputCountFingerprinting:
    """Test input/output count heuristics."""

    @pytest.mark.unit
    def test_single_output_sweep(self):
        """Single output suggests sweep or consolidation."""
        tx = make_tx(vout=[
            {"n": 0, "value": "1.0", "scriptPubKey": {"hex": "0014" + "0" * 40}},
        ])
        hints = detect_fingerprints(tx)
        assert any("Single output" in h for h in hints)
        assert any("sweep" in h.lower() or "consolidation" in h.lower() for h in hints)

    @pytest.mark.unit
    def test_two_outputs_typical(self):
        """Two outputs is typical payment + change."""
        tx = make_tx(vout=[
            {"n": 0, "value": "1.0", "scriptPubKey": {"hex": "0014" + "0" * 40}},
            {"n": 1, "value": "0.5", "scriptPubKey": {"hex": "0014" + "1" * 40}},
        ])
        hints = detect_fingerprints(tx)
        assert any("Two outputs" in h for h in hints)

    @pytest.mark.unit
    def test_many_inputs_consolidation(self):
        """Many inputs suggest UTXO consolidation."""
        tx = make_tx(
            vin=[{"sequence": 0xFFFFFFFD, "txid": f"tx{i}", "vout": 0} for i in range(10)],
            vout=[{"n": 0, "value": "10.0", "scriptPubKey": {"hex": "0014" + "0" * 40}}],
        )
        hints = detect_fingerprints(tx)
        assert any("10 inputs" in h for h in hints)
        assert any("consolidation" in h.lower() or "high-volume" in h.lower() for h in hints)


class TestCoinbaseDetection:
    """Test coinbase transaction handling."""

    @pytest.mark.unit
    def test_coinbase_input(self):
        """Coinbase transactions have special input."""
        tx = {
            "version": 2,
            "locktime": 0,
            "vin": [{"coinbase": "0320a107...", "sequence": 0xFFFFFFFF}],
            "vout": [{"n": 0, "value": "6.25", "scriptPubKey": {"hex": "0014" + "0" * 40}}],
        }
        hints = detect_fingerprints(tx)
        # Should handle coinbase without crashing
        assert isinstance(hints, list)


class TestCombinedFingerprinting:
    """Test realistic transactions with multiple fingerprints."""

    @pytest.mark.unit
    def test_hardware_wallet_signature(self):
        """Hardware wallets often have distinctive patterns."""
        tx = make_tx(
            version=1,        # Often v1
            locktime=0,       # Often 0
            vin=[{"sequence": 0xFFFFFFFF}],  # No RBF, no locktime
            vout=[
                {"n": 0, "value": "1.0", "scriptPubKey": {"hex": "0014" + "0" * 40}},
                {"n": 1, "value": "0.5", "scriptPubKey": {"hex": "0014" + "1" * 40}},
            ],
        )
        hints = detect_fingerprints(tx)
        # Multiple hints should be generated
        assert len(hints) >= 3
        assert any("locktime=0" in h for h in hints)
        assert any("version=1" in h for h in hints)

    @pytest.mark.unit
    def test_modern_wallet_signature(self):
        """Modern wallets use v2 with RBF and anti-fee-sniping."""
        tx = make_tx(
            version=2,
            locktime=850000,  # Recent block height
            vin=[{"sequence": 0xFFFFFFFD}],  # RBF enabled
            vout=[
                {"n": 0, "value": "0.05", "scriptPubKey": {"hex": "5120" + "0" * 64}},  # P2TR
                {"n": 1, "value": "0.01234567", "scriptPubKey": {"hex": "5120" + "1" * 64}},  # P2TR
            ],
        )
        hints = detect_fingerprints(tx)
        assert any("version=2" in h for h in hints)
        assert any("BIP-125" in h or "RBF" in h for h in hints)
        assert any("anti-fee-sniping" in h for h in hints)


class TestEdgeCases:
    """Test edge cases and potential crashes."""

    @pytest.mark.unit
    def test_empty_transaction(self):
        """Empty transaction dict shouldn't crash."""
        hints = detect_fingerprints({})
        assert isinstance(hints, list)

    @pytest.mark.unit
    def test_missing_fields(self):
        """Transaction missing optional fields."""
        tx = {"vin": [], "vout": []}
        hints = detect_fingerprints(tx)
        assert isinstance(hints, list)

    @pytest.mark.unit
    def test_string_values(self):
        """Handle string value amounts."""
        tx = make_tx(vout=[
            {"n": 0, "value": "1.00000000", "scriptPubKey": {"hex": "0014" + "0" * 40}},
        ])
        hints = detect_fingerprints(tx)
        # Should handle string values
        assert any("round" in h.lower() for h in hints)

    @pytest.mark.unit
    def test_decimal_values(self):
        """Handle Decimal value amounts."""
        tx = make_tx(vout=[
            {"n": 0, "value": Decimal("1.0"), "scriptPubKey": {"hex": "0014" + "0" * 40}},
        ])
        hints = detect_fingerprints(tx)
        assert isinstance(hints, list)

    @pytest.mark.unit
    def test_zero_value_output(self):
        """OP_RETURN outputs often have 0 value."""
        tx = make_tx(vout=[
            {"n": 0, "value": "0", "scriptPubKey": {"hex": "6a0b68656c6c6f"}},  # OP_RETURN
            {"n": 1, "value": "1.0", "scriptPubKey": {"hex": "0014" + "0" * 40}},
        ])
        hints = detect_fingerprints(tx)
        # Should not flag 0-value as round amount
        assert not any("Output #0" in h and "round" in h.lower() for h in hints)
