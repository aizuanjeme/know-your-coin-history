# Know Your Coin History

A Bitcoin transaction history explorer with visual graph tracing, wallet fingerprint detection, and BIP-329 label management.

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-3.x-green.svg)
![Bitcoin Core](https://img.shields.io/badge/Bitcoin%20Core-22+-orange.svg)

## Features

- **Transaction Tracing** — Recursively trace any UTXO back through its parent transactions
- **Interactive Graph** — Visual transaction flow diagrams (vis.js)
- **Wallet Fingerprinting** — Detect round amounts, RBF signaling, mixed script types
- **BIP-329 Labels** — Import/export wallet labels in standard JSONL format
- **Freeze Outputs** — Mark UTXOs as non-spendable
- **Script Detection** — Identify P2PKH, P2SH, P2WPKH, P2WSH, P2TR

## Quick Start

```bash
# 1. Clone and setup
git clone https://github.com/aizuanjeme/know-your-coin-history.git
cd know-your-coin-history
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Start Bitcoin Core (regtest)
bitcoind -datadir=$PWD/datadir/node0

# 3. Run the app
python app.py
```

Open **http://127.0.0.1:5000** in your browser.

For detailed setup instructions, see [docs/SETUP.md](docs/SETUP.md).

## Project Structure

```
know-your-coin-history/
├── app.py              # Flask web server
├── bitcoin_rpc.py      # Bitcoin Core RPC client
├── coin_history.py     # Transaction tracing logic
├── requirements.txt    # Python dependencies
├── labels.jsonl        # Your saved labels
├── templates/
│   └── index.html      # Web interface
├── datadir/
│   └── node0/          # Bitcoin Core data
└── docs/
    ├── SETUP.md        # Setup guide
    ├── CREDENTIALS.md  # RPC credentials explained
    ├── ARCHITECTURE.md # System design
    └── EXPLAINED.md    # ELI5 explanation
```

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/trace` | POST | Trace transaction history |
| `/api/tx/<txid>` | GET | Transaction details |
| `/api/utxos` | GET | List wallet UTXOs |
| `/api/labels` | GET/POST | List/add labels |
| `/api/labels/<ref>` | DELETE | Delete label |
| `/api/labels/export` | GET | Download BIP-329 file |
| `/api/labels/import` | POST | Upload BIP-329 file |

### Example

```bash
# Trace a transaction
curl -X POST http://127.0.0.1:5000/api/trace \
  -H "Content-Type: application/json" \
  -d '{"txid": "abc123...", "depth": 5}'
```

## Documentation

| Document | Description |
|----------|-------------|
| [SETUP.md](docs/SETUP.md) | Step-by-step installation guide |
| [CREDENTIALS.md](docs/CREDENTIALS.md) | How RPC credentials were chosen |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design and data flow |
| [EXPLAINED.md](docs/EXPLAINED.md) | Simple explanation (ELI5) |
| [TESTING.md](docs/TESTING.md) | Testing methodology & coverage |

## Testing

Run the test suite to verify functionality:

```bash
# Run all tests (140 tests, ~1 second)
python -m pytest tests/ -v

# Run with coverage (87% coverage on core modules)
python -m pytest tests/ --cov=coin_history --cov-report=term

# Run only unit tests (no RPC needed)
python -m pytest tests/ -m unit
```

See [docs/TESTING.md](docs/TESTING.md) for full testing methodology.

## Configuration

Default RPC settings (can override with environment variables):

```bash
export RPC_URL="http://127.0.0.1:18443"
export RPC_USER="admin"
export RPC_PASS="history2026"
export WALLET="student"
```

See [docs/CREDENTIALS.md](docs/CREDENTIALS.md) for why these credentials were chosen.

## BIP-329 Labels

Labels are stored in JSONL format per [BIP-329](https://github.com/bitcoin/bips/blob/master/bip-0329.mediawiki):

```json
{"type": "tx", "ref": "abc123...", "label": "Payment from Alice"}
{"type": "output", "ref": "abc123...:0", "label": "My change", "spendable": true}
{"type": "addr", "ref": "bc1q...", "label": "Cold storage"}
```

## Acknowledgments

- Inspired by [0xB10C/project-ideas#13](https://github.com/0xB10C/project-ideas/issues/13)
- Graph visualization: [vis.js](https://visjs.org/)
- Label format: [BIP-329](https://github.com/bitcoin/bips/blob/master/bip-0329.mediawiki)

## License

MIT
# know-your-coin-history
