"""
Bitcoin Core JSON-RPC client.

A minimal wrapper using only the `requests` library.
No external Bitcoin packages required.
"""

import requests
from typing import Any, List, Optional


class BitcoinRPC:
    """
    Simple wrapper around Bitcoin Core's JSON-RPC interface.
    
    Example:
        rpc = BitcoinRPC(user="admin", password="history2026", wallet="student")
        print(rpc.getblockcount())
    """

    def __init__(
        self,
        url: str = "http://127.0.0.1:18443",
        user: str = "admin",
        password: str = "history2026",
        wallet: Optional[str] = None,
    ):
        self.url = url
        self.user = user
        self.password = password
        self.wallet = wallet
        self._id = 0

    def _endpoint(self) -> str:
        """Build the RPC endpoint URL, including wallet path if set."""
        if self.wallet:
            return f"{self.url}/wallet/{self.wallet}"
        return self.url

    def call(self, method: str, params: Optional[List[Any]] = None) -> Any:
        """
        Make a JSON-RPC call to Bitcoin Core.
        
        Raises RPCError if the node returns an error.
        """
        self._id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._id,
            "method": method,
            "params": params or [],
        }
        resp = requests.post(
            self._endpoint(),
            json=payload,
            auth=(self.user, self.password),
            timeout=120,
        )
        body = resp.json()
        if body.get("error"):
            raise RPCError(body["error"])
        return body["result"]

    # --- Convenience methods for common RPC calls ---

    def getblockcount(self) -> int:
        return self.call("getblockcount")

    def getblockhash(self, height: int) -> str:
        return self.call("getblockhash", [height])

    def getblock(self, blockhash: str, verbosity: int = 1) -> dict:
        return self.call("getblock", [blockhash, verbosity])

    def getrawtransaction(self, txid: str, verbose: bool = True) -> dict:
        return self.call("getrawtransaction", [txid, verbose])

    def decoderawtransaction(self, hex_str: str) -> dict:
        return self.call("decoderawtransaction", [hex_str])

    def listunspent(self, minconf: int = 0, maxconf: int = 9999999) -> list:
        return self.call("listunspent", [minconf, maxconf])

    def getbalances(self) -> dict:
        return self.call("getbalances")

    def createwallet(self, name: str, disable_private_keys: bool = False, blank: bool = True):
        return self.call("createwallet", [name, disable_private_keys, blank])

    def loadwallet(self, name: str):
        return self.call("loadwallet", [name])

    def importdescriptors(self, descriptors: list):
        return self.call("importdescriptors", descriptors)

    def listwallets(self) -> list:
        return self.call("listwallets")

    def scantxoutset(self, action: str, scanobjects: list):
        return self.call("scantxoutset", [action, scanobjects])


class RPCError(Exception):
    def __init__(self, error: dict):
        self.code = error.get("code", -1)
        self.message = error.get("message", str(error))
        super().__init__(f"RPC error {self.code}: {self.message}")
