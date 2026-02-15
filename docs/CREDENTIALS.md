# RPC Credentials

This document explains the Bitcoin Core RPC authentication setup used in this project.

---

## How the Credentials Were Chosen

We set up **two RPC users** with different permission levels:

### 1. `admin` user (Full access)

| Property | Value |
|----------|-------|
| Username | `admin` |
| Password | `history2026` |
| Purpose  | Unrestricted access for the Coin History tool |

**Why this password?**
- `history` — reflects the project name "Know Your Coin History"
- `2026` — the year this project was created (February 2026)
- Combined: `history2026` — easy to remember, clearly tied to this project

This user has **no RPC whitelist restrictions** (`rpcwhitelistdefault=0`), allowing it to call any RPC method. The Coin History tool needs this to:
- Fetch raw transactions (`getrawtransaction`)
- Decode transactions (`decoderawtransaction`)
- List wallet UTXOs (`listunspent`)
- Get block information (`getblock`, `getblockheader`)

### 2. `student` user (Limited access)

| Property | Value |
|----------|-------|
| Username | `student` |
| Password | `boss2026` |
| Purpose  | Restricted access for wallet operations only |

**Why this password?**
- `boss` — a simple memorable word
- `2026` — consistency with the admin password year

This user is **whitelisted** to only call specific methods:
```
listunspent, getrawchangeaddress, createrawtransaction, 
signrawtransactionwithwallet, sendrawtransaction, getbalances, 
getblockcount, createwallet, importdescriptors, generatetoaddress, stop
```

---

## How the Credentials Were Generated

Bitcoin Core uses `rpcauth` for secure authentication. The password is never stored in plaintext — only a **salted hash**.

### Step 1: Generate the hash

Bitcoin Core includes a helper script. You can also use this Python snippet:

```python
import hashlib
import secrets

def generate_rpcauth(username, password):
    salt = secrets.token_hex(16)
    password_hmac = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode(),
        salt.encode(),
        1000
    ).hex()
    return f"rpcauth={username}:{salt}${password_hmac}"

# Generate for admin user
print(generate_rpcauth("admin", "history2026"))
# Output: rpcauth=admin:ac1937a24c0a362ef4713659692472de$c9785e532972667da8aaae505a5d3567be966318905a149a6c6e842aec80d3f5

# Generate for student user  
print(generate_rpcauth("student", "boss2026"))
# Output: rpcauth=student:9e2a740807c433cad4e1ceba17d5a4eb$fb01f6ab01ede71d28d6c7928e1d9ebd31637a3a83bec3ae798579a7f4997e15
```

### Step 2: Add to bitcoin.conf

```ini
# admin user for coin history tool (password: history2026)
rpcauth=admin:ac1937a24c0a362ef4713659692472de$c9785e532972667da8aaae505a5d3567be966318905a149a6c6e842aec80d3f5

# student user with limited permissions (password: boss2026)
rpcauth=student:9e2a740807c433cad4e1ceba17d5a4eb$fb01f6ab01ede71d28d6c7928e1d9ebd31637a3a83bec3ae798579a7f4997e15
```

---

## Security Notes

### For Development (regtest)

The included credentials are fine for local development on regtest. The `regtest` network is completely isolated — it has no real Bitcoin value.

### For Production (mainnet/testnet)

If you deploy this on mainnet or testnet:

1. **Generate new credentials** — Don't use the default passwords
2. **Use strong passwords** — At least 16 random characters
3. **Restrict network access** — Only allow localhost connections (`rpcbind=127.0.0.1`)
4. **Use environment variables** — Don't commit real credentials to git

```bash
# Example: Set credentials via environment
export RPC_USER="your_secure_username"
export RPC_PASS="$(openssl rand -base64 32)"
```

---

## Quick Reference

| User | Password | Access Level | Use Case |
|------|----------|--------------|----------|
| `admin` | `history2026` | Full (unrestricted) | Coin History tool |
| `student` | `boss2026` | Limited (whitelisted) | Wallet operations |

### Connecting with bitcoin-cli

```bash
# As admin (full access)
bitcoin-cli -datadir=$PWD/datadir/node0 -rpcuser=admin -rpcpassword=history2026 getblockchaininfo

# As student (limited access)
bitcoin-cli -datadir=$PWD/datadir/node0 -rpcuser=student -rpcpassword=boss2026 getbalances
```

### Connecting in Python

```python
from bitcoin_rpc import BitcoinRPC

rpc = BitcoinRPC(
    url="http://127.0.0.1:18443",
    user="admin",
    password="history2026",
    wallet="student"
)
```
