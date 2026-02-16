# Testing Methodology

> "Don't trust, verify" - Bitcoin Proverb

This project uses comprehensive automated testing to ensure correctness and prevent regressions.

## Quick Start

```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage report
python -m pytest tests/ --cov=coin_history --cov=bitcoin_rpc --cov-report=term

# Run specific test categories
python -m pytest tests/ -m unit           # Pure unit tests (fast)
python -m pytest tests/ -m integration    # Tests with mocked RPC
python -m pytest tests/ -m api            # Flask API tests
```

## Test Coverage

| Module | Coverage | Description |
|--------|----------|-------------|
| `coin_history.py` | 92% | Core tracing and label logic |
| `bitcoin_rpc.py` | 50% | RPC wrapper (requires live node for full testing) |
| **Total** | **87%** | Combined coverage |

## Test Categories

### 1. Unit Tests (`@pytest.mark.unit`)

Pure functions tested without I/O or network calls. These are fast and deterministic.

**Script Type Identification** ([test_script_types.py](tests/test_script_types.py))
- P2PKH, P2SH, P2WPKH, P2WSH, P2TR pattern matching
- Edge cases: malformed scripts, empty inputs, case sensitivity
- "Tricky coins" that might fool naive pattern matching

**Wallet Fingerprinting** ([test_fingerprinting.py](tests/test_fingerprinting.py))
- Transaction version detection (v1/v2/v3)
- Locktime analysis (block height vs timestamp)
- nSequence analysis (RBF signaling)
- Round amount detection
- Input/output count heuristics

**BIP-329 Labels** ([test_labels.py](tests/test_labels.py))
- CRUD operations (create, read, update, delete)
- All BIP-329 field types (tx, addr, output, input, pubkey, xpub)
- Frozen output tracking
- JSONL import/export
- Validation and error handling

### 2. Integration Tests (`@pytest.mark.integration`)

Tests with mocked Bitcoin RPC to verify tracing logic.

**CoinHistory Tracer** ([test_coin_history.py](tests/test_coin_history.py))
- Transaction tracing with depth limits
- Graph data generation for visualization
- Coinbase transaction handling
- Cycle detection (visited set)
- Fee calculation
- Label integration

### 3. API Tests (`@pytest.mark.api`)

Flask HTTP endpoint tests.

**API Endpoints** ([test_api.py](tests/test_api.py))
- Label management (POST/GET/DELETE)
- BIP-329 export/import
- Transaction tracing endpoint
- Error handling (400/404/502 responses)

## Test Scenarios

### Simple Cases
- Basic P2WPKH spend (1 input → 2 outputs)
- Coinbase transaction
- Label creation and retrieval

### Tricky Coins
- Scripts that start like P2PKH but aren't
- Mixed output types (privacy leak detection)
- OP_RETURN containing P2PKH-like data
- Future SegWit versions (v2+)

### Edge Cases
- Empty/null inputs
- Missing transaction fields
- Very deep trace chains
- Malformed RPC responses

### Regression Tests
The test suite serves as regression tests. After modifying any code:

```bash
# Run the full suite to verify nothing broke
python -m pytest tests/ -v

# Check coverage didn't drop
python -m pytest tests/ --cov=coin_history --cov-report=term
```

## Adding New Tests

### For Pure Functions

```python
# tests/test_my_feature.py
import pytest
from coin_history import my_new_function

class TestMyFeature:
    @pytest.mark.unit
    def test_basic_case(self):
        """Test the most common use case."""
        result = my_new_function("input")
        assert result == "expected"

    @pytest.mark.unit
    def test_edge_case(self):
        """Test boundary conditions."""
        assert my_new_function("") == "default"
        assert my_new_function(None) == "default"
```

### For RPC-Dependent Code

```python
# Use mocked RPC
from unittest.mock import Mock
from coin_history import CoinHistory

@pytest.fixture
def mock_rpc():
    rpc = Mock()
    rpc.getrawtransaction.return_value = {...}
    return rpc

def test_with_mock(mock_rpc):
    history = CoinHistory(mock_rpc)
    result = history.trace("txid", max_depth=5)
    assert ...
```

## Continuous Integration

Run tests before every commit:

```bash
# Pre-commit hook example
python -m pytest tests/ -v --tb=short
if [ $? -ne 0 ]; then
    echo "Tests failed! Fix before committing."
    exit 1
fi
```

## Philosophy

1. **Test behavior, not implementation** - Tests verify what the code does, not how
2. **Fast feedback** - Unit tests run in <1 second
3. **Isolation** - Tests don't depend on external services
4. **Clarity** - Test names describe expected behavior
5. **Coverage** - Aim for 80%+ on core logic
