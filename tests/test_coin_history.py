"""
Tests for CoinHistory transaction tracer.

These tests use mocked RPC to simulate Bitcoin Core responses.
This allows testing the tracing logic without a running node.

Run with: pytest tests/test_coin_history.py -v
"""

import pytest
from unittest.mock import Mock, patch
from decimal import Decimal

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from coin_history import CoinHistory
from bitcoin_rpc import BitcoinRPC


# ============================================================================
# Test Fixtures - Mock transactions for different scenarios
# ============================================================================

def make_p2wpkh_spk(address="bc1qtest"):
    """Create a P2WPKH scriptPubKey dict."""
    return {
        "hex": "0014" + "89abcdef" * 5,  # 44 chars = P2WPKH
        "address": address,
        "type": "witness_v0_keyhash",
    }


def make_p2tr_spk(address="bc1ptest"):
    """Create a P2TR scriptPubKey dict."""
    return {
        "hex": "5120" + "00" * 32,  # 68 chars = P2TR
        "address": address,
        "type": "witness_v1_taproot",
    }


def make_coinbase_tx(txid, value="6.25"):
    """Create a coinbase transaction."""
    return {
        "txid": txid,
        "version": 2,
        "locktime": 0,
        "size": 200,
        "vsize": 170,
        "weight": 680,
        "confirmations": 100,
        "blockhash": "0000000000000000000abc",
        "vin": [{"coinbase": "0320a107...", "sequence": 0xFFFFFFFF}],
        "vout": [{
            "n": 0,
            "value": value,
            "scriptPubKey": make_p2wpkh_spk("bc1qminer"),
        }],
    }


def make_simple_tx(txid, prev_txid, prev_vout, value_in, value_out, change=None):
    """Create a simple spend transaction."""
    vout = [{
        "n": 0,
        "value": str(value_out),
        "scriptPubKey": make_p2wpkh_spk("bc1qrecipient"),
    }]
    
    if change is not None:
        vout.append({
            "n": 1,
            "value": str(change),
            "scriptPubKey": make_p2wpkh_spk("bc1qchange"),
        })
    
    return {
        "txid": txid,
        "version": 2,
        "locktime": 800000,
        "size": 250,
        "vsize": 140,
        "weight": 560,
        "confirmations": 10,
        "blockhash": "0000000000000000000def",
        "vin": [{
            "txid": prev_txid,
            "vout": prev_vout,
            "sequence": 0xFFFFFFFD,
        }],
        "vout": vout,
    }


@pytest.fixture
def mock_rpc():
    """Create a mock BitcoinRPC."""
    rpc = Mock(spec=BitcoinRPC)
    rpc.getblockcount.return_value = 850000
    return rpc


@pytest.fixture
def coin_history(mock_rpc):
    """Create CoinHistory with mocked RPC."""
    return CoinHistory(mock_rpc)


# ============================================================================
# Basic Tracing Tests
# ============================================================================

class TestBasicTracing:
    """Test basic transaction tracing functionality."""

    @pytest.mark.integration
    def test_trace_single_tx(self, coin_history, mock_rpc):
        """Trace a single transaction (no parents)."""
        tx = make_coinbase_tx("tx1")
        mock_rpc.getrawtransaction.return_value = tx
        
        coin_history.trace("tx1", max_depth=0)
        
        data = coin_history.graph_data()
        assert "tx1" in coin_history.nodes
        assert coin_history.nodes["tx1"]["type"] == "tx"

    @pytest.mark.integration
    def test_trace_with_parent(self, coin_history, mock_rpc):
        """Trace a transaction with one parent."""
        parent_tx = make_coinbase_tx("parent", "50.0")
        child_tx = make_simple_tx("child", "parent", 0, 50.0, 49.9, 0.1)
        
        def get_tx(txid, verbose=True):
            if txid == "child":
                return child_tx
            elif txid == "parent":
                return parent_tx
            return None
        
        mock_rpc.getrawtransaction.side_effect = get_tx
        
        coin_history.trace("child", max_depth=5)
        
        # Should have both transactions
        assert "child" in coin_history.nodes
        assert "parent" in coin_history.nodes
        # Should have the outpoint from parent
        assert "parent:0" in coin_history.nodes

    @pytest.mark.integration
    def test_trace_respects_max_depth(self, coin_history, mock_rpc):
        """Tracing should stop at max_depth."""
        # Create chain: grandparent -> parent -> child
        grandparent = make_coinbase_tx("grandparent", "50.0")
        parent = make_simple_tx("parent", "grandparent", 0, 50.0, 49.9)
        child = make_simple_tx("child", "parent", 0, 49.9, 49.8)
        
        def get_tx(txid, verbose=True):
            return {"grandparent": grandparent, "parent": parent, "child": child}.get(txid)
        
        mock_rpc.getrawtransaction.side_effect = get_tx
        
        # Trace with depth=1 should only get child and parent
        coin_history.trace("child", max_depth=1)
        
        assert "child" in coin_history.nodes
        assert "parent" in coin_history.nodes
        # Grandparent should NOT be in nodes (as a tx node)
        tx_nodes = [n for n in coin_history.nodes.values() if n.get("type") == "tx"]
        assert len(tx_nodes) == 2  # Only child and parent

    @pytest.mark.integration
    def test_trace_handles_coinbase(self, coin_history, mock_rpc):
        """Coinbase inputs should create special coinbase nodes."""
        coinbase_tx = make_coinbase_tx("coinbase_tx")
        mock_rpc.getrawtransaction.return_value = coinbase_tx
        
        coin_history.trace("coinbase_tx", max_depth=5)
        
        # Should have coinbase node
        cb_id = "coinbase:coinbase_tx"
        assert cb_id in coin_history.nodes
        assert coin_history.nodes[cb_id]["type"] == "coinbase"

    @pytest.mark.integration
    def test_trace_avoids_cycles(self, coin_history, mock_rpc):
        """Tracing should not revisit already-traced transactions."""
        tx = make_coinbase_tx("tx1")
        
        call_count = 0
        def counting_get_tx(txid, verbose=True):
            nonlocal call_count
            call_count += 1
            return tx
        
        mock_rpc.getrawtransaction.side_effect = counting_get_tx
        
        # Trace same TX twice
        coin_history.trace("tx1", max_depth=5)
        coin_history.trace("tx1", max_depth=5)  # Should not re-trace
        
        # If cycle detection works, second call shouldn't hit RPC again
        # (it's cached after first call)
        assert call_count == 1


# ============================================================================
# Graph Data Tests
# ============================================================================

class TestGraphData:
    """Test graph data generation for visualization."""

    @pytest.mark.integration
    def test_graph_has_nodes_and_edges(self, coin_history, mock_rpc):
        """Graph data should have nodes and edges."""
        tx = make_coinbase_tx("tx1")
        mock_rpc.getrawtransaction.return_value = tx
        
        coin_history.trace("tx1", max_depth=0)
        data = coin_history.graph_data()
        
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) > 0

    @pytest.mark.integration
    def test_output_nodes_have_address(self, coin_history, mock_rpc):
        """UTXO nodes should include address info."""
        tx = {
            "txid": "tx1",
            "version": 2,
            "locktime": 0,
            "size": 200,
            "vsize": 170,
            "weight": 680,
            "confirmations": 100,
            "vin": [{"coinbase": "...", "sequence": 0xFFFFFFFF}],
            "vout": [{
                "n": 0,
                "value": "1.0",
                "scriptPubKey": {
                    "hex": "0014" + "00" * 20,
                    "address": "bc1qspecificaddress",
                    "type": "witness_v0_keyhash",
                },
            }],
        }
        mock_rpc.getrawtransaction.return_value = tx
        
        coin_history.trace("tx1", max_depth=0)
        
        outpoint_node = coin_history.nodes.get("tx1:0")
        assert outpoint_node is not None
        assert outpoint_node["address"] == "bc1qspecificaddress"
        assert outpoint_node["script_type"] == "P2WPKH"

    @pytest.mark.integration
    def test_edges_connect_correctly(self, coin_history, mock_rpc):
        """Edges should connect tx -> outputs and inputs -> tx."""
        parent = make_coinbase_tx("parent", "1.0")
        child = make_simple_tx("child", "parent", 0, 1.0, 0.9)
        
        def get_tx(txid, verbose=True):
            return {"parent": parent, "child": child}.get(txid)
        
        mock_rpc.getrawtransaction.side_effect = get_tx
        
        coin_history.trace("child", max_depth=5)
        data = coin_history.graph_data()
        
        # Should have edge: parent:0 -> child (input spending)
        input_edges = [e for e in data["edges"] if e["to"] == "child" and e["from"] == "parent:0"]
        assert len(input_edges) == 1
        
        # Should have edge: child -> child:0 (output creation)
        output_edges = [e for e in data["edges"] if e["from"] == "child" and e["to"] == "child:0"]
        assert len(output_edges) == 1


class TestResetGraph:
    """Test graph reset functionality."""

    @pytest.mark.integration
    def test_reset_clears_data(self, coin_history, mock_rpc):
        """reset_graph() should clear all data."""
        tx = make_coinbase_tx("tx1")
        mock_rpc.getrawtransaction.return_value = tx
        
        coin_history.trace("tx1", max_depth=0)
        assert len(coin_history.nodes) > 0
        
        coin_history.reset_graph()
        
        assert len(coin_history.nodes) == 0
        assert len(coin_history.edges) == 0


# ============================================================================
# Transaction Summary Tests
# ============================================================================

class TestTxSummary:
    """Test transaction summary generation."""

    @pytest.mark.integration
    def test_summary_includes_fingerprints(self, coin_history, mock_rpc):
        """Summary should include fingerprinting info."""
        tx = make_coinbase_tx("tx1")
        mock_rpc.getrawtransaction.return_value = tx
        
        summary = coin_history.tx_summary("tx1")
        
        assert summary is not None
        assert "fingerprints" in summary
        assert isinstance(summary["fingerprints"], list)

    @pytest.mark.integration
    def test_summary_calculates_fee(self, coin_history, mock_rpc):
        """Summary should calculate transaction fee."""
        parent = {
            "txid": "parent",
            "vout": [{
                "n": 0,
                "value": "1.0",
                "scriptPubKey": make_p2wpkh_spk(),
            }],
        }
        
        child = {
            "txid": "child",
            "version": 2,
            "locktime": 0,
            "size": 200,
            "vsize": 140,
            "weight": 560,
            "confirmations": 10,
            "vin": [{"txid": "parent", "vout": 0, "sequence": 0xFFFFFFFD}],
            "vout": [{
                "n": 0,
                "value": "0.9999",  # Fee = 0.0001 BTC = 10000 sats
                "scriptPubKey": make_p2wpkh_spk(),
            }],
        }
        
        def get_tx(txid, verbose=True):
            return {"parent": parent, "child": child}.get(txid)
        
        mock_rpc.getrawtransaction.side_effect = get_tx
        
        summary = coin_history.tx_summary("child")
        
        # Values come back as Decimal strings
        assert Decimal(summary["total_in"]) == Decimal("1.0")
        assert Decimal(summary["total_out"]) == Decimal("0.9999")
        assert Decimal(summary["fee_btc"]) == Decimal("0.0001")

    @pytest.mark.integration
    def test_summary_includes_labels(self, coin_history, mock_rpc):
        """Summary should include user labels."""
        tx = make_coinbase_tx("tx1")
        mock_rpc.getrawtransaction.return_value = tx
        
        # Add a label
        coin_history.labels.add("tx", "tx1", "My labeled transaction")
        
        summary = coin_history.tx_summary("tx1")
        assert summary["label"] == "My labeled transaction"

    @pytest.mark.integration
    def test_summary_missing_tx(self, coin_history, mock_rpc):
        """Summary of non-existent TX returns None."""
        mock_rpc.getrawtransaction.side_effect = Exception("TX not found")
        
        summary = coin_history.tx_summary("nonexistent")
        assert summary is None


# ============================================================================
# Wallet Coins Tests
# ============================================================================

class TestListWalletCoins:
    """Test wallet UTXO listing with spendability info."""

    @pytest.mark.integration
    def test_list_enriches_utxos(self, coin_history, mock_rpc):
        """list_wallet_coins() should enrich UTXOs with extra info."""
        mock_rpc.listunspent.return_value = [{
            "txid": "utxo_tx",
            "vout": 0,
            "address": "bc1qtest",
            "amount": 1.0,
            "confirmations": 10,
            "spendable": True,
            "solvable": True,
            "safe": True,
            "scriptPubKey": "0014" + "00" * 20,
        }]
        
        coins = coin_history.list_wallet_coins()
        
        assert len(coins) == 1
        assert "script_type" in coins[0]
        assert "spendability" in coins[0]

    @pytest.mark.integration
    def test_frozen_utxo_not_spendable(self, coin_history, mock_rpc):
        """Frozen UTXOs should show as not spendable."""
        mock_rpc.listunspent.return_value = [{
            "txid": "frozen_tx",
            "vout": 0,
            "address": "bc1qtest",
            "amount": 1.0,
            "confirmations": 10,
            "spendable": True,
            "solvable": True,
            "safe": True,
            "scriptPubKey": "0014" + "00" * 20,
        }]
        
        # Freeze the UTXO
        coin_history.labels.add("output", "frozen_tx:0", "Frozen", spendable=False)
        
        coins = coin_history.list_wallet_coins()
        
        assert coins[0]["spendability"]["frozen"] is True
        assert coins[0]["spendability"]["can_spend"] is False

    @pytest.mark.integration
    def test_watch_only_utxo(self, coin_history, mock_rpc):
        """Watch-only UTXOs should show correct reason."""
        mock_rpc.listunspent.return_value = [{
            "txid": "watch_tx",
            "vout": 0,
            "address": "bc1qtest",
            "amount": 1.0,
            "confirmations": 10,
            "spendable": False,  # Watch-only
            "solvable": True,
            "safe": True,
            "scriptPubKey": "0014" + "00" * 20,
        }]
        
        coins = coin_history.list_wallet_coins()
        
        assert coins[0]["spendability"]["has_key"] is False
        assert "Watch-only" in coins[0]["spendability"]["reason"]


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.integration
    def test_missing_parent_tx(self, coin_history, mock_rpc):
        """Gracefully handle missing parent transactions."""
        child = make_simple_tx("child", "missing_parent", 0, 1.0, 0.9)
        
        def get_tx(txid, verbose=True):
            if txid == "child":
                return child
            raise Exception("TX not found")
        
        mock_rpc.getrawtransaction.side_effect = get_tx
        
        # Should not crash
        coin_history.trace("child", max_depth=5)
        
        # Child should still be in graph
        assert "child" in coin_history.nodes

    @pytest.mark.integration
    def test_malformed_tx_data(self, coin_history, mock_rpc):
        """Handle malformed transaction data gracefully."""
        malformed = {
            "txid": "malformed",
            # Missing most fields
        }
        mock_rpc.getrawtransaction.return_value = malformed
        
        # Should not crash
        coin_history.trace("malformed", max_depth=0)

    @pytest.mark.integration
    def test_very_deep_trace(self, coin_history, mock_rpc):
        """Deep traces should respect max_depth limit."""
        # Create a chain of 100 transactions
        def get_tx(txid, verbose=True):
            depth = int(txid.replace("tx", ""))
            if depth == 0:
                return make_coinbase_tx(txid)
            return make_simple_tx(txid, f"tx{depth-1}", 0, 50.0 - depth * 0.1, 50.0 - (depth + 1) * 0.1)
        
        mock_rpc.getrawtransaction.side_effect = get_tx
        
        coin_history.trace("tx50", max_depth=5)
        
        # Should have at most ~6 tx nodes (tx50 through tx45)
        tx_nodes = [n for n in coin_history.nodes.values() if n.get("type") == "tx"]
        assert len(tx_nodes) <= 10  # Some buffer for implementation details


# ============================================================================
# Integration with Labels
# ============================================================================

class TestLabelIntegration:
    """Test that labels integrate properly with tracing."""

    @pytest.mark.integration
    def test_labels_persist_across_traces(self, coin_history, mock_rpc):
        """Labels should persist when graph is reset."""
        tx = make_coinbase_tx("tx1")
        mock_rpc.getrawtransaction.return_value = tx
        
        # Add label
        coin_history.labels.add("tx", "tx1", "Important TX")
        
        # Trace and reset
        coin_history.trace("tx1", max_depth=0)
        coin_history.reset_graph()
        
        # Label should still exist
        assert coin_history.labels.get_label("tx1") == "Important TX"

    @pytest.mark.integration
    def test_output_labels_in_summary(self, coin_history, mock_rpc):
        """Output labels should appear in tx summary."""
        tx = make_coinbase_tx("tx1")
        mock_rpc.getrawtransaction.return_value = tx
        
        # Label the output
        coin_history.labels.add("output", "tx1:0", "Mining reward")
        
        summary = coin_history.tx_summary("tx1")
        assert summary["outputs"][0]["label"] == "Mining reward"
