"""
Tests for BIP-329 Label Manager.

BIP-329 defines a standard format for wallet label import/export.
These tests verify compliance with the specification.

Run with: pytest tests/test_labels.py -v
"""

import pytest
import json
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from coin_history import LabelManager


@pytest.fixture
def label_manager():
    """Fresh LabelManager for each test."""
    return LabelManager()


class TestLabelTypes:
    """Test BIP-329 label type validation."""

    @pytest.mark.unit
    def test_valid_types(self, label_manager):
        """All BIP-329 types should be accepted."""
        valid_types = ["tx", "addr", "pubkey", "input", "output", "xpub"]
        
        for t in valid_types:
            entry = label_manager.add(t, f"ref_{t}", f"label for {t}")
            assert entry["type"] == t
            assert entry["ref"] == f"ref_{t}"

    @pytest.mark.unit
    def test_invalid_type(self, label_manager):
        """Invalid types should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            label_manager.add("invalid_type", "ref", "label")
        assert "Invalid type" in str(exc_info.value)

    @pytest.mark.unit
    def test_type_case_sensitivity(self, label_manager):
        """Types should be case-sensitive per BIP-329."""
        with pytest.raises(ValueError):
            label_manager.add("TX", "ref", "label")  # Should be lowercase


class TestBasicCRUD:
    """Test Create, Read, Update, Delete operations."""

    @pytest.mark.unit
    def test_add_and_get(self, label_manager):
        """Add a label and retrieve it."""
        ref = "abc123def456"
        label_manager.add("tx", ref, "Test transaction")
        
        entry = label_manager.get(ref)
        assert entry is not None
        assert entry["type"] == "tx"
        assert entry["label"] == "Test transaction"

    @pytest.mark.unit
    def test_get_label_text(self, label_manager):
        """get_label() returns just the label text."""
        label_manager.add("tx", "mytx", "My Label")
        assert label_manager.get_label("mytx") == "My Label"

    @pytest.mark.unit
    def test_get_missing_label(self, label_manager):
        """Missing labels return empty string."""
        assert label_manager.get_label("nonexistent") == ""
        assert label_manager.get("nonexistent") is None

    @pytest.mark.unit
    def test_update_existing(self, label_manager):
        """Adding same ref updates the entry."""
        label_manager.add("tx", "mytx", "Original")
        label_manager.add("tx", "mytx", "Updated")
        
        assert label_manager.get_label("mytx") == "Updated"
        assert len(label_manager.all_labels()) == 1

    @pytest.mark.unit
    def test_delete(self, label_manager):
        """Delete a label."""
        label_manager.add("tx", "mytx", "To be deleted")
        assert label_manager.delete("mytx") is True
        assert label_manager.get("mytx") is None

    @pytest.mark.unit
    def test_delete_missing(self, label_manager):
        """Deleting non-existent label returns False."""
        assert label_manager.delete("nonexistent") is False

    @pytest.mark.unit
    def test_clear(self, label_manager):
        """Clear all labels."""
        label_manager.add("tx", "tx1", "Label 1")
        label_manager.add("addr", "addr1", "Label 2")
        label_manager.clear()
        assert len(label_manager.all_labels()) == 0


class TestBIP329Fields:
    """Test BIP-329 optional fields for each type."""

    @pytest.mark.unit
    def test_tx_fields(self, label_manager):
        """Transaction labels support height, time, fee, value, rate."""
        entry = label_manager.add(
            "tx",
            "abc123",
            "Exchange withdrawal",
            height=800000,
            time="2024-01-15T10:30:00Z",
            fee=500,
            value=-100000,
            rate={"USD": 43000.00},
        )
        
        assert entry["height"] == 800000
        assert entry["time"] == "2024-01-15T10:30:00Z"
        assert entry["fee"] == 500
        assert entry["value"] == -100000
        assert entry["rate"] == {"USD": 43000.00}

    @pytest.mark.unit
    def test_output_spendable(self, label_manager):
        """Output labels support spendable field."""
        entry = label_manager.add(
            "output",
            "abc123:0",
            "Frozen UTXO",
            spendable=False,
        )
        
        assert entry["spendable"] is False

    @pytest.mark.unit
    def test_spendable_only_for_output(self, label_manager):
        """spendable field should only be set for output type."""
        entry = label_manager.add(
            "tx",
            "abc123",
            "Transaction",
            spendable=False,  # Should be ignored
        )
        
        assert "spendable" not in entry

    @pytest.mark.unit
    def test_address_fields(self, label_manager):
        """Address labels support keypath and heights."""
        entry = label_manager.add(
            "addr",
            "bc1qtest123",
            "Cold storage",
            keypath="/0/123",
            heights=[100000, 200000, 300000],
        )
        
        assert entry["keypath"] == "/0/123"
        assert entry["heights"] == [100000, 200000, 300000]

    @pytest.mark.unit
    def test_input_output_fmv(self, label_manager):
        """Input/output labels support fair market value."""
        entry = label_manager.add(
            "input",
            "abc123:0",
            "FIFO cost basis",
            value=100000,
            fmv={"USD": 43.00},
        )
        
        assert entry["value"] == 100000
        assert entry["fmv"] == {"USD": 43.00}

    @pytest.mark.unit
    def test_origin_field(self, label_manager):
        """All types support origin descriptor."""
        entry = label_manager.add(
            "addr",
            "bc1qtest",
            "My address",
            origin="wpkh([d34db33f/84h/0h/0h])",
        )
        
        assert entry["origin"] == "wpkh([d34db33f/84h/0h/0h])"

    @pytest.mark.unit
    def test_label_max_length(self, label_manager):
        """Labels should be truncated to 255 chars (BIP-329 recommendation)."""
        long_label = "x" * 300
        entry = label_manager.add("tx", "abc", long_label)
        
        assert len(entry.get("label", "")) <= 255


class TestFrozenOutputs:
    """Test frozen output tracking."""

    @pytest.mark.unit
    def test_frozen_outputs_list(self, label_manager):
        """frozen_outputs() returns list of non-spendable outputs."""
        label_manager.add("output", "tx1:0", "Frozen", spendable=False)
        label_manager.add("output", "tx2:1", "Frozen too", spendable=False)
        label_manager.add("output", "tx3:0", "Spendable", spendable=True)
        label_manager.add("tx", "tx4", "Transaction")  # Not an output
        
        frozen = label_manager.frozen_outputs()
        assert "tx1:0" in frozen
        assert "tx2:1" in frozen
        assert "tx3:0" not in frozen
        assert "tx4" not in frozen

    @pytest.mark.unit
    def test_unfreeze_output(self, label_manager):
        """Update output to make it spendable."""
        label_manager.add("output", "tx1:0", "Frozen", spendable=False)
        assert "tx1:0" in label_manager.frozen_outputs()
        
        label_manager.add("output", "tx1:0", "Unfrozen", spendable=True)
        assert "tx1:0" not in label_manager.frozen_outputs()


class TestByType:
    """Test filtering labels by type."""

    @pytest.mark.unit
    def test_by_type(self, label_manager):
        """by_type() returns labels of specific type."""
        label_manager.add("tx", "tx1", "Transaction 1")
        label_manager.add("tx", "tx2", "Transaction 2")
        label_manager.add("addr", "addr1", "Address 1")
        label_manager.add("output", "tx1:0", "Output 1")
        
        txs = label_manager.by_type("tx")
        assert len(txs) == 2
        assert all(e["type"] == "tx" for e in txs)
        
        addrs = label_manager.by_type("addr")
        assert len(addrs) == 1

    @pytest.mark.unit
    def test_by_type_empty(self, label_manager):
        """by_type() returns empty list for no matches."""
        label_manager.add("tx", "tx1", "Transaction")
        assert label_manager.by_type("xpub") == []


class TestImportExport:
    """Test BIP-329 JSONL import/export."""

    @pytest.mark.unit
    def test_export_string(self, label_manager):
        """Export to JSONL string."""
        label_manager.add("tx", "abc123", "My TX")
        label_manager.add("addr", "bc1qtest", "My Address")
        
        output = label_manager.export_bip329_string()
        lines = [l for l in output.split("\n") if l.strip()]
        
        assert len(lines) == 2
        
        # Each line should be valid JSON
        for line in lines:
            entry = json.loads(line)
            assert "type" in entry
            assert "ref" in entry

    @pytest.mark.unit
    def test_import_string(self, label_manager):
        """Import from JSONL string."""
        data = '{"type":"tx","ref":"abc123","label":"Imported TX"}\n'
        data += '{"type":"addr","ref":"bc1qtest","label":"Imported Addr"}\n'
        
        count = label_manager.import_bip329_string(data)
        
        assert count == 2
        assert label_manager.get_label("abc123") == "Imported TX"
        assert label_manager.get_label("bc1qtest") == "Imported Addr"

    @pytest.mark.unit
    def test_export_import_roundtrip(self, label_manager):
        """Data survives export/import cycle."""
        label_manager.add("tx", "tx1", "Transaction", height=800000, fee=500)
        label_manager.add("output", "tx1:0", "Frozen", spendable=False, value=100000)
        
        exported = label_manager.export_bip329_string()
        
        # Import into fresh manager
        manager2 = LabelManager()
        manager2.import_bip329_string(exported)
        
        # Verify data
        assert manager2.get_label("tx1") == "Transaction"
        assert manager2.get("tx1")["height"] == 800000
        assert "tx1:0" in manager2.frozen_outputs()

    @pytest.mark.unit
    def test_import_file(self, label_manager):
        """Import from actual file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"type":"tx","ref":"from_file","label":"From File"}\n')
            f.flush()
            
            count = label_manager.import_bip329(f.name)
            
        assert count == 1
        assert label_manager.get_label("from_file") == "From File"
        Path(f.name).unlink()

    @pytest.mark.unit
    def test_export_file(self, label_manager):
        """Export to actual file."""
        label_manager.add("tx", "to_file", "To File")
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
            
        count = label_manager.export_bip329(path)
        
        assert count == 1
        
        # Read back
        with open(path) as f:
            content = f.read()
        assert "to_file" in content
        assert "To File" in content
        
        Path(path).unlink()


class TestImportValidation:
    """Test BIP-329 import validation."""

    @pytest.mark.unit
    def test_skip_invalid_json(self, label_manager):
        """Invalid JSON lines are skipped per BIP-329."""
        data = '{"type":"tx","ref":"valid","label":"Valid"}\n'
        data += 'not json at all\n'
        data += '{"type":"tx","ref":"also_valid","label":"Also Valid"}\n'
        
        count = label_manager.import_bip329_string(data)
        
        assert count == 2
        assert label_manager.get("valid") is not None
        assert label_manager.get("also_valid") is not None

    @pytest.mark.unit
    def test_skip_empty_lines(self, label_manager):
        """Empty lines are skipped."""
        data = '{"type":"tx","ref":"tx1","label":"TX1"}\n\n\n{"type":"tx","ref":"tx2","label":"TX2"}\n'
        
        count = label_manager.import_bip329_string(data)
        assert count == 2

    @pytest.mark.unit
    def test_reject_missing_type(self, label_manager):
        """Entries without type are rejected."""
        data = '{"ref":"no_type","label":"Missing Type"}\n'
        
        count = label_manager.import_bip329_string(data)
        assert count == 0

    @pytest.mark.unit
    def test_reject_missing_ref(self, label_manager):
        """Entries without ref are rejected."""
        data = '{"type":"tx","label":"Missing Ref"}\n'
        
        count = label_manager.import_bip329_string(data)
        assert count == 0

    @pytest.mark.unit
    def test_reject_invalid_type(self, label_manager):
        """Entries with invalid type are rejected."""
        data = '{"type":"notavalidtype","ref":"test","label":"Invalid Type"}\n'
        
        count = label_manager.import_bip329_string(data)
        assert count == 0

    @pytest.mark.unit
    def test_reject_spendable_on_non_output(self, label_manager):
        """spendable field on non-output types should be rejected."""
        # Per BIP-329, spendable is only valid for output type
        data = '{"type":"tx","ref":"test","label":"TX","spendable":false}\n'
        
        count = label_manager.import_bip329_string(data)
        assert count == 0  # Should reject


class TestBackwardsCompatibility:
    """Test backwards compatibility with old API."""

    @pytest.mark.unit
    def test_set_label_alias(self, label_manager):
        """set_label() should work but use add() internally."""
        label_manager.set_label("tx", "tx1", "Old API", origin="test")
        
        assert label_manager.get_label("tx1") == "Old API"
        assert label_manager.get("tx1")["origin"] == "test"

    @pytest.mark.unit
    def test_delete_label_alias(self, label_manager):
        """delete_label() should work but use delete() internally."""
        label_manager.add("tx", "tx1", "To delete")
        label_manager.delete_label("tx1")
        
        assert label_manager.get("tx1") is None


class TestRealWorldScenarios:
    """Test realistic usage scenarios."""

    @pytest.mark.unit
    def test_exchange_withdrawal_tracking(self, label_manager):
        """Track exchange withdrawal with tax info."""
        label_manager.add(
            "tx",
            "abc123def456789",
            "Coinbase withdrawal",
            height=800000,
            time="2024-01-15T10:30:00Z",
            fee=500,
            value=100000000,  # 1 BTC in
            rate={"USD": 43000.00},
        )
        
        label_manager.add(
            "output",
            "abc123def456789:0",
            "Cold storage",
            value=99999500,
            fmv={"USD": 42999.785},
            spendable=True,
        )
        
        tx_entry = label_manager.get("abc123def456789")
        assert tx_entry["rate"]["USD"] == 43000.00

    @pytest.mark.unit
    def test_suspicious_source_freeze(self, label_manager):
        """Freeze UTXO from suspicious source."""
        # Mark as frozen
        label_manager.add(
            "output",
            "suspicious_tx:0",
            "⚠️ Possible mixer output - DO NOT SPEND",
            spendable=False,
        )
        
        assert "suspicious_tx:0" in label_manager.frozen_outputs()

    @pytest.mark.unit
    def test_address_book_with_activity(self, label_manager):
        """Track address with transaction heights."""
        label_manager.add(
            "addr",
            "bc1qexchangehotw4llet123",
            "Kraken Hot Wallet",
            heights=[700000, 750000, 800000],
        )
        
        entry = label_manager.get("bc1qexchangehotw4llet123")
        assert len(entry["heights"]) == 3
