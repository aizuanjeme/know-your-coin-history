# Setup Guide

Step-by-step instructions to run **Know Your Coin History** on your local machine.

---

## Prerequisites

- **Python 3.9+** installed
- **Bitcoin Core v0.21+** installed (tested with v30.2.0)
- macOS, Linux, or Windows with WSL

---

## 1. Clone the Repository

```bash
git clone https://github.com/aizuanjeme/know-your-coin-history.git
cd know-your-coin-history
```

---

## 2. Set Up Python Environment

Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## 3. Configure Bitcoin Core

The project includes a pre-configured `datadir/node0/bitcoin.conf` for **regtest** (local testing network).

### Option A: Use the included regtest setup

The config file is already set up with:
- Network: `regtest` (isolated local blockchain)
- RPC enabled on port `18443`
- Transaction indexing enabled (`txindex=1`)
- Two RPC users configured (see [CREDENTIALS.md](CREDENTIALS.md))

Start Bitcoin Core with the included datadir:

```bash
bitcoind -datadir=$PWD/datadir/node0
```

### Option B: Use your own Bitcoin Core setup

If you want to use your existing Bitcoin Core installation:

1. Ensure these settings are in your `bitcoin.conf`:
   ```ini
   server=1
   txindex=1
   rpcuser=YOUR_USER
   rpcpassword=YOUR_PASSWORD
   ```

2. Set environment variables before running the app:
   ```bash
   export RPC_URL="http://127.0.0.1:8332"      # mainnet: 8332, testnet: 18332, regtest: 18443
   export RPC_USER="YOUR_USER"
   export RPC_PASS="YOUR_PASSWORD"
   export WALLET="your_wallet_name"
   ```

---

## 4. Create a Wallet (First Time Only)

If using the included regtest setup for the first time:

```bash
# Create the student wallet
bitcoin-cli -datadir=$PWD/datadir/node0 -rpcuser=admin -rpcpassword=history2026 createwallet "student"

# Generate some test coins (regtest only)
bitcoin-cli -datadir=$PWD/datadir/node0 -rpcuser=admin -rpcpassword=history2026 -rpcwallet=student -generate 101
```

---

## 5. Run the Application

```bash
python app.py
```

You should see:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Know Your Coin History
  RPC → http://127.0.0.1:18443  (wallet: student)
  Labels file → /path/to/labels.jsonl
  Open http://127.0.0.1:5000 in your browser
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Open **http://127.0.0.1:5000** in your browser.

---

## 6. Basic Usage

1. **Trace a Transaction**: Enter a TXID in the search box and click "Trace"
2. **Add Labels**: Click on any transaction node to view details and add labels
3. **View UTXOs**: The sidebar shows your wallet's unspent outputs
4. **Export Labels**: Download your labels as a BIP-329 compatible JSONL file

---

## Troubleshooting

### "Connection refused" error
- Make sure bitcoind is running: `bitcoin-cli -datadir=$PWD/datadir/node0 -rpcuser=admin -rpcpassword=history2026 getblockcount`

### "Wallet not found" error
- Load or create the wallet: `bitcoin-cli -datadir=$PWD/datadir/node0 -rpcuser=admin -rpcpassword=history2026 loadwallet "student"`

### Port 5000 already in use
- Kill the existing process: `lsof -ti:5000 | xargs kill -9`
- Or on macOS, disable AirPlay Receiver in System Settings > General > AirDrop & Handoff

### RPC authentication failed (403)
- Verify credentials match what's in `bitcoin.conf`
- Check that `rpcwhitelistdefault=0` is set in `bitcoin.conf`

---

## Project Structure

```
know-your-coin-history/
├── app.py              # Flask web server and API routes
├── bitcoin_rpc.py      # Bitcoin Core RPC client
├── coin_history.py     # Transaction tracing and label management
├── requirements.txt    # Python dependencies
├── labels.jsonl        # Your saved labels (BIP-329 format)
├── templates/
│   └── index.html      # Web interface
├── datadir/
│   └── node0/          # Bitcoin Core data directory
│       └── bitcoin.conf
└── docs/
    ├── SETUP.md        # This file
    ├── CREDENTIALS.md  # RPC credentials explanation
    ├── ARCHITECTURE.md # System design
    └── EXPLAINED.md    # ELI5 explanation
```

---

## Next Steps

- Read [ARCHITECTURE.md](ARCHITECTURE.md) to understand the system design
- Read [EXPLAINED.md](EXPLAINED.md) for a simple explanation of how it works
- Check [CREDENTIALS.md](CREDENTIALS.md) for details on the RPC authentication setup
