# System Architecture

## Overview

Know Your Coin History is a web-based Bitcoin transaction explorer built with a **layered architecture**. It enables users to trace UTXO histories, visualize transaction graphs, and manage wallet labels using the BIP-329 standard.

```
┌─────────────────────────────────────────────────────────────────┐
│                        Web Browser                               │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │              vis.js Transaction Graph UI                 │   │
│   │  ┌─────────┐ ┌─────────────┐ ┌─────────────────────┐   │   │
│   │  │ Graph   │ │ TX Details  │ │ Labels / UTXOs      │   │   │
│   │  │ Canvas  │ │ Panel       │ │ Management          │   │   │
│   │  └─────────┘ └─────────────┘ └─────────────────────────┘   │
│   └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP/REST API
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Flask Web Server                            │
│                        (app.py)                                  │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  Routes:                                                 │   │
│   │  • POST /api/trace      - Trace transaction history     │   │
│   │  • GET  /api/tx/<txid>  - Get transaction summary       │   │
│   │  • GET  /api/utxos      - List wallet UTXOs             │   │
│   │  • *    /api/labels     - BIP-329 label management      │   │
│   │  • GET  /api/wallets    - List available wallets        │   │
│   └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ Function Calls
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Core Logic Layer                              │
│                    (coin_history.py)                             │
│   ┌─────────────────┐  ┌─────────────────┐  ┌───────────────┐   │
│   │   CoinHistory   │  │  LabelManager   │  │  Fingerprint  │   │
│   │   - trace()     │  │  - add()        │  │  Detection    │   │
│   │   - tx_summary()│  │  - export()     │  │  Functions    │   │
│   │   - BFS crawl   │  │  - import()     │  │               │   │
│   └─────────────────┘  └─────────────────┘  └───────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ JSON-RPC
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Bitcoin RPC Client                            │
│                    (bitcoin_rpc.py)                              │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  BitcoinRPC Class:                                       │   │
│   │  • call(method, params)  - Generic RPC call              │   │
│   │  • getrawtransaction()   - Get full transaction data     │   │
│   │  • listunspent()         - Get wallet UTXOs              │   │
│   │  • getblockcount()       - Get current block height      │   │
│   └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP POST (JSON-RPC)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Bitcoin Core Node                            │
│                     (bitcoind)                                   │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  • regtest network                                       │   │
│   │  • txindex=1 (full transaction index)                    │   │
│   │  • RPC server on port 18443                              │   │
│   │  • Wallet: student_wallet                                │   │
│   └─────────────────────────────────────────────────────────┘   │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  Data Directory:                                         │   │
│   │  datadir/node0/                                          │   │
│   │    ├── bitcoin.conf                                      │   │
│   │    └── regtest/                                          │   │
│   │        ├── blocks/                                       │   │
│   │        └── wallets/                                      │   │
│   └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Component Details

### 1. Frontend (templates/index.html)

| Component | Technology | Purpose |
|-----------|------------|---------|
| Graph Visualization | vis-network 9.1.6 | Interactive transaction flow diagrams |
| Network Requests | Fetch API | REST API communication |
| UI Framework | Vanilla HTML/CSS | Single-page application |

**Features:**
- Real-time graph updates on trace
- Click-to-select transaction details
- Import/export BIP-329 labels
- UTXO list with script type indicators

### 2. Web Server (app.py)

**Framework:** Flask 3.x with development server

**API Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Serve the main UI page |
| POST | `/api/trace` | Trace transaction history, returns nodes/edges |
| GET | `/api/tx/<txid>` | Get detailed transaction summary |
| GET | `/api/utxos` | List all wallet UTXOs with addresses |
| GET | `/api/labels` | Get all BIP-329 labels as JSON |
| POST | `/api/labels` | Add a new label |
| DELETE | `/api/labels/<ref>` | Remove a label |
| GET | `/api/wallets` | List available wallets |

### 3. Core Logic (coin_history.py)

**CoinHistory Class:**
- `trace(txid, max_depth)`: BFS traversal of transaction inputs
- `tx_summary(txid)`: Detailed transaction analysis including fingerprints
- Returns graph data as `{nodes: [], edges: []}`

**LabelManager Class:**
- BIP-329 compliant label storage
- Supports: `tx`, `addr`, `pubkey`, `input`, `output`, `xpub` types
- File format: JSONL (one JSON object per line)

**Fingerprint Detection:**
- Round payment amounts
- Low-fee transactions
- RBF signaling (nSequence < 0xFFFFFFFE)
- Mixed script types
- Large input counts
- Change output heuristics

### 4. RPC Client (bitcoin_rpc.py)

**BitcoinRPC Class:**
- JSON-RPC 1.0 over HTTP
- Basic authentication with username/password
- Automatic wallet path handling
- Error wrapping with `RPCError` exception

**Key Methods:**
```python
rpc.call("method", [params])              # Generic call
rpc.getrawtransaction(txid, verbose=True) # Get decoded TX
rpc.listunspent(minconf=0)                # Get wallet coins
rpc.getblockcount()                       # Current height
```

---

## Data Flow

### Tracing a Transaction

```
User enters TXID
       │
       ▼
POST /api/trace {txid, depth}
       │
       ▼
CoinHistory.trace()
       │
       ├──► For each transaction:
       │    1. getrawtransaction(txid)
       │    2. Extract vin[] inputs
       │    3. Queue parent TXIDs
       │    4. Build node/edge lists
       │
       ▼
Return {nodes: [...], edges: [...]}
       │
       ▼
vis.js renders interactive graph
```

### Adding a Label

```
User clicks "Add Label"
       │
       ▼
POST /api/labels {type, ref, label}
       │
       ▼
LabelManager.add(type, ref, label)
       │
       ▼
Append to labels.jsonl file
       │
       ▼
Update UI label list
```

---

## Running the System

### Prerequisites

- **Python 3.8+** with pip
- **Bitcoin Core 22.0+** with txindex enabled
- **Virtual environment** (recommended)

### Step-by-Step Startup

#### 1. Start Bitcoin Core

```bash
# Navigate to project directory
cd "/Users/aizuanjeme/Development/web3/portfolio/coin history"

# Start bitcoind with the data directory
bitcoind -datadir="$PWD/datadir/node0" -daemon
```

#### 2. Verify Bitcoin is Running

```bash
# Check block count
bitcoin-cli -datadir="$PWD/datadir/node0" \
            -rpcuser=admin -rpcpassword=history2026 \
            getblockcount
```

#### 3. Activate Python Environment

```bash
# Activate virtual environment
source venv/bin/activate

# Install dependencies (first time only)
pip install -r requirements.txt
```

#### 4. Start Flask Server

```bash
# Run the web application
python app.py
```

#### 5. Access the Application

Open in browser: **http://127.0.0.1:5000**

---

## Configuration Files

### bitcoin.conf

```ini
# Network
regtest=1

# Indexing (required for transaction lookup)
txindex=1

# RPC Server
server=1
rpcbind=127.0.0.1
rpcallowip=127.0.0.1

# Authentication
rpcauth=admin:...
rpcauth=student:...

# CRITICAL: Allow admin full access
rpcwhitelistdefault=0

# Student permissions (limited)
rpcwhitelist=student:getblockcount,getbalance,...
```

### Environment Variables (Optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `BITCOIN_RPC_URL` | `http://127.0.0.1:18443` | Bitcoin RPC endpoint |
| `RPC_USER` | `admin` | RPC username |
| `RPC_PASS` | `history2026` | RPC password |
| `FLASK_PORT` | `5000` | Web server port |

---

## Security Considerations

1. **RPC Credentials**: Store in environment variables, not in code
2. **Network Binding**: RPC only on localhost (127.0.0.1)
3. **Wallet Permissions**: Use `rpcwhitelist` for restricted users
4. **Debug Mode**: Disable in production (`debug=False`)

---

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| "Connection refused" | bitcoind not running | Start with `bitcoind -daemon` |
| "403 Forbidden" | RPC user blocked | Set `rpcwhitelistdefault=0` |
| "Transaction not found" | txindex disabled | Add `txindex=1`, restart, reindex |
| Graph not loading | vis.js CDN issue | Check network/console errors |
| Empty UTXO list | Wrong wallet loaded | Check wallet name in app.py |
