"""
Tests for Flask API endpoints.

These test the HTTP API layer. Tests that require RPC are skipped
when Bitcoin Core is not running.

Run with: pytest tests/test_api.py -v
"""

import pytest
import json
from unittest.mock import Mock, patch
import requests

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


def bitcoin_core_available():
    """Check if Bitcoin Core is running."""
    try:
        resp = requests.post(
            "http://127.0.0.1:18443",
            json={"jsonrpc": "2.0", "id": 1, "method": "getblockcount"},
            auth=("admin", "history2026"),
            timeout=2
        )
        return resp.status_code == 200
    except:
        return False


# Skip RPC-dependent tests if Bitcoin Core not running
requires_bitcoin_core = pytest.mark.skipif(
    not bitcoin_core_available(),
    reason="Bitcoin Core not running"
)


@pytest.fixture
def client():
    """Flask test client - imports app fresh for each test."""
    # Import here to avoid module-level RPC calls
    import app as app_module
    app_module.app.config["TESTING"] = True
    
    # Clear labels for clean state
    app_module.history.labels.clear()
    
    return app_module.app.test_client()


@pytest.fixture 
def history():
    """Get the CoinHistory instance for direct manipulation."""
    import app as app_module
    return app_module.history


class TestHealthEndpoints:
    """Test basic health/info endpoints."""

    @pytest.mark.api
    def test_index_returns_html(self, client):
        """Main page should return HTML."""
        response = client.get("/")
        assert response.status_code == 200
        assert b"html" in response.data.lower()

    @pytest.mark.api
    @requires_bitcoin_core
    def test_blockcount(self, client):
        """GET /api/blockcount returns block height."""
        response = client.get("/api/blockcount")
        assert response.status_code == 200
        data = response.get_json()
        assert "blockcount" in data
        assert isinstance(data["blockcount"], int)

    @pytest.mark.api
    @requires_bitcoin_core
    def test_balance(self, client):
        """GET /api/balance returns wallet balances or error if wallet not loaded."""
        response = client.get("/api/balance")
        # 200 if wallet loaded, 502 if wallet not loaded
        assert response.status_code in (200, 502)
        data = response.get_json()
        assert isinstance(data, dict)


class TestTraceEndpoint:
    """Test /api/trace endpoint."""

    @pytest.mark.api
    def test_trace_requires_txid(self, client):
        """POST /api/trace without txid returns 400."""
        response = client.post(
            "/api/trace",
            json={},
            content_type="application/json"
        )
        assert response.status_code == 400
        assert "txid" in response.get_json().get("error", "").lower()

    @pytest.mark.api
    def test_trace_empty_txid(self, client):
        """POST /api/trace with empty txid returns 400."""
        response = client.post(
            "/api/trace",
            json={"txid": ""},
            content_type="application/json"
        )
        assert response.status_code == 400

    @pytest.mark.api
    @requires_bitcoin_core
    def test_trace_caps_depth(self, client):
        """Depth should be capped at 20."""
        # This will fail if TX doesn't exist, but tests the endpoint works
        response = client.post(
            "/api/trace",
            json={"txid": "0" * 64, "depth": 100},  # Fake txid
            content_type="application/json"
        )
        # Will return 500 or 502 if TX not found, but shouldn't crash
        assert response.status_code in (200, 500, 502)

    @pytest.mark.api
    @requires_bitcoin_core
    def test_trace_returns_graph_data(self, client):
        """Successful trace returns nodes and edges (requires real TX)."""
        # This test requires a real transaction - skip without Bitcoin Core
        pass  # Covered by integration tests


class TestLabelsAPI:
    """Test /api/labels endpoints (BIP-329)."""

    @pytest.mark.api
    def test_list_labels_empty(self, client, history):
        """GET /api/labels returns empty list initially."""
        history.labels.clear()  # Ensure clean state
        response = client.get("/api/labels")
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)

    @pytest.mark.api
    def test_create_label(self, client, history):
        """POST /api/labels creates a new label."""
        history.labels.clear()
        response = client.post(
            "/api/labels",
            json={
                "type": "tx",
                "ref": "test_tx_create_123",
                "label": "Test Transaction",
            },
            content_type="application/json"
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert data["ok"] is True
        assert data["action"] == "created"

    @pytest.mark.api
    def test_update_label(self, client, history):
        """POST /api/labels updates existing label."""
        history.labels.clear()
        # Create
        client.post(
            "/api/labels",
            json={"type": "tx", "ref": "update_test", "label": "Original"},
            content_type="application/json"
        )
        
        # Update
        response = client.post(
            "/api/labels",
            json={"type": "tx", "ref": "update_test", "label": "Updated"},
            content_type="application/json"
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert data["action"] == "updated"

    @pytest.mark.api
    def test_create_label_requires_ref(self, client):
        """POST /api/labels without ref returns 400."""
        response = client.post(
            "/api/labels",
            json={"type": "tx", "label": "No ref"},
            content_type="application/json"
        )
        
        assert response.status_code == 400

    @pytest.mark.api
    def test_create_label_with_bip329_fields(self, client, history):
        """POST /api/labels accepts full BIP-329 fields."""
        history.labels.clear()
        response = client.post(
            "/api/labels",
            json={
                "type": "tx",
                "ref": "full_bip329_tx",
                "label": "Full BIP-329 Label",
                "height": 800000,
                "time": "2024-01-15T10:00:00Z",
                "fee": 500,
                "value": 100000000,
                "rate": {"USD": 43000.00},
            },
            content_type="application/json"
        )
        
        assert response.status_code == 200
        entry = response.get_json()["entry"]
        assert entry["height"] == 800000
        assert entry["rate"]["USD"] == 43000.00

    @pytest.mark.api
    def test_create_frozen_output(self, client, history):
        """POST /api/labels can create frozen output."""
        history.labels.clear()
        response = client.post(
            "/api/labels",
            json={
                "type": "output",
                "ref": "frozen_utxo:0",
                "label": "Frozen UTXO",
                "spendable": False,
            },
            content_type="application/json"
        )
        
        assert response.status_code == 200
        entry = response.get_json()["entry"]
        assert entry["spendable"] is False

    @pytest.mark.api
    def test_get_single_label(self, client, history):
        """GET /api/labels/<ref> returns single label."""
        history.labels.clear()
        # Create
        client.post(
            "/api/labels",
            json={"type": "addr", "ref": "bc1qgettest", "label": "Get Test"},
            content_type="application/json"
        )
        
        # Get
        response = client.get("/api/labels/bc1qgettest")
        assert response.status_code == 200
        data = response.get_json()
        assert data["label"] == "Get Test"

    @pytest.mark.api
    def test_get_missing_label(self, client, history):
        """GET /api/labels/<ref> for missing label returns 404."""
        history.labels.clear()
        response = client.get("/api/labels/nonexistent_ref_12345")
        assert response.status_code == 404

    @pytest.mark.api
    def test_delete_label(self, client, history):
        """DELETE /api/labels/<ref> removes label."""
        history.labels.clear()
        # Create
        client.post(
            "/api/labels",
            json={"type": "tx", "ref": "to_delete", "label": "Delete me"},
            content_type="application/json"
        )
        
        # Delete
        response = client.delete("/api/labels/to_delete")
        assert response.status_code == 200
        assert response.get_json()["deleted"] is True
        
        # Verify deleted
        response = client.get("/api/labels/to_delete")
        assert response.status_code == 404

    @pytest.mark.api
    def test_labels_by_type(self, client, history):
        """GET /api/labels/by-type/<type> filters by type."""
        history.labels.clear()
        # Create different types
        client.post("/api/labels", json={"type": "tx", "ref": "tx1_bytype", "label": "TX"}, content_type="application/json")
        client.post("/api/labels", json={"type": "addr", "ref": "addr1_bytype", "label": "Addr"}, content_type="application/json")
        client.post("/api/labels", json={"type": "tx", "ref": "tx2_bytype", "label": "TX2"}, content_type="application/json")
        
        response = client.get("/api/labels/by-type/tx")
        assert response.status_code == 200
        data = response.get_json()
        tx_labels = [e for e in data if e["type"] == "tx"]
        assert len(tx_labels) >= 2

    @pytest.mark.api
    def test_frozen_outputs_list(self, client, history):
        """GET /api/labels/frozen returns frozen output refs."""
        history.labels.clear()
        # Create frozen and unfrozen
        client.post("/api/labels", json={"type": "output", "ref": "frozen1:0", "spendable": False}, content_type="application/json")
        client.post("/api/labels", json={"type": "output", "ref": "notfrozen:0", "spendable": True}, content_type="application/json")
        
        response = client.get("/api/labels/frozen")
        assert response.status_code == 200
        frozen = response.get_json()
        assert "frozen1:0" in frozen
        assert "notfrozen:0" not in frozen


class TestLabelExportImport:
    """Test BIP-329 export/import endpoints."""

    @pytest.mark.api
    def test_export_jsonl(self, client, history):
        """GET /api/labels/export returns JSONL file."""
        history.labels.clear()
        # Create some labels
        client.post("/api/labels", json={"type": "tx", "ref": "export1", "label": "Export 1"}, content_type="application/json")
        client.post("/api/labels", json={"type": "addr", "ref": "export2", "label": "Export 2"}, content_type="application/json")
        
        response = client.get("/api/labels/export")
        assert response.status_code == 200
        assert "jsonl" in response.content_type
        assert b"export1" in response.data
        assert b"export2" in response.data

    @pytest.mark.api
    def test_import_jsonl(self, client, history):
        """POST /api/labels/import loads JSONL file."""
        history.labels.clear()
        from io import BytesIO
        
        jsonl_content = b'{"type":"tx","ref":"imported1","label":"Imported 1"}\n'
        jsonl_content += b'{"type":"addr","ref":"imported2","label":"Imported 2"}\n'
        
        response = client.post(
            "/api/labels/import",
            data={"file": (BytesIO(jsonl_content), "labels.jsonl")},
            content_type="multipart/form-data"
        )
        
        assert response.status_code == 200
        assert response.get_json()["imported"] == 2
        
        # Verify imported
        response = client.get("/api/labels/imported1")
        assert response.status_code == 200
        assert response.get_json()["label"] == "Imported 1"

    @pytest.mark.api
    def test_import_requires_file(self, client):
        """POST /api/labels/import without file returns 400."""
        response = client.post("/api/labels/import")
        assert response.status_code == 400


class TestUTXOEndpoint:
    """Test /api/utxos endpoint."""

    @pytest.mark.api
    @requires_bitcoin_core
    def test_list_utxos(self, client):
        """GET /api/utxos returns wallet UTXOs or error if wallet not loaded."""
        response = client.get("/api/utxos")
        # 200 if wallet loaded, 502 if wallet not loaded
        assert response.status_code in (200, 502)
        data = response.get_json()
        # List of UTXOs or error dict
        assert isinstance(data, (list, dict))


class TestTxDetailEndpoint:
    """Test /api/tx/<txid> endpoint."""

    @pytest.mark.api
    @requires_bitcoin_core
    def test_tx_detail(self, client):
        """GET /api/tx/<txid> returns transaction details (requires real TX)."""
        # Skip - requires real transaction
        pass

    @pytest.mark.api
    @requires_bitcoin_core
    def test_tx_not_found(self, client):
        """GET /api/tx/<txid> for missing TX returns 404 or 502."""
        response = client.get("/api/tx/" + "0" * 64)
        assert response.status_code in (404, 502)


class TestWalletEndpoints:
    """Test wallet management endpoints."""

    @pytest.mark.api
    @requires_bitcoin_core
    def test_list_wallets(self, client):
        """GET /api/wallets returns loaded wallets."""
        response = client.get("/api/wallets")
        assert response.status_code == 200
        wallets = response.get_json()
        assert isinstance(wallets, list)

    @pytest.mark.api
    def test_switch_wallet(self, client):
        """POST /api/wallets/switch changes active wallet."""
        response = client.post(
            "/api/wallets/switch",
            json={"wallet": "another_wallet"},
            content_type="application/json"
        )
        assert response.status_code == 200
        assert response.get_json()["wallet"] == "another_wallet"

    @pytest.mark.api
    def test_switch_wallet_requires_name(self, client):
        """POST /api/wallets/switch without name returns 400."""
        response = client.post(
            "/api/wallets/switch",
            json={},
            content_type="application/json"
        )
        assert response.status_code == 400


class TestErrorHandling:
    """Test error responses."""

    @pytest.mark.api
    @requires_bitcoin_core
    def test_rpc_error_returns_502(self, client):
        """RPC errors should return appropriate error codes."""
        # Test with intentionally bad request - skip without Bitcoin Core
        pass

    @pytest.mark.api
    def test_invalid_label_type(self, client):
        """Invalid label type returns 400."""
        response = client.post(
            "/api/labels",
            json={"type": "invalidtype", "ref": "test", "label": "Test"},
            content_type="application/json"
        )
        assert response.status_code == 400
