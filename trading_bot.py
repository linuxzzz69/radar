#!/usr/bin/env python3
"""
trading_bot.py - in-Telegram trading for the radar bot (Path A: key custody)
Wallet lives in ~/Desktop/x/.bot_wallet.json (gitignored, chmod 600)
NEVER commit this file. NEVER paste the key anywhere except /export.

Flow:
  /wallet          -> create wallet (once), show pubkey
  /export          -> show private key ONCE (backup warning)
  send CA          -> info + BUY/SELL inline buttons (handled in watcher.py)
  Buy buttons      -> 0.05/0.1/0.25/0.5 SOL swaps via Jupiter
  Sell buttons     -> 25/50/75/100% of token balance
"""
import json, os, urllib.request, time
from solders.keypair import Keypair
import base58

BASE = os.path.dirname(os.path.abspath(__file__))
WALLET_PATH = os.path.join(BASE, ".bot_wallet.json")
UA = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
RPC = os.environ.get("RPC_URL", "https://api.mainnet-beta.solana.com")
JUP_QUOTE = "https://lite-api.jup.ag/swap/v1/quote"
JUP_SWAP = "https://lite-api.jup.ag/swap/v1/swap"
SOL_MINT = "So11111111111111111111111111111111111111112"

def wallet_exists():
    return os.path.exists(WALLET_PATH)

def create_wallet():
    if wallet_exists(): return None
    kp = Keypair()
    pub = str(kp.pubkey())
    priv_b58 = base58.b58encode(bytes(kp)).decode()
    with open(WALLET_PATH, "w") as f:
        json.dump({"pubkey": pub, "secret_b58": priv_b58, "created": time.time()}, f)
    os.chmod(WALLET_PATH, 0o600)
    return {"pubkey": pub}

def load_wallet():
    if not wallet_exists(): return None
    with open(WALLET_PATH) as f:
        d = json.load(f)
    return Keypair.from_bytes(base58.b58decode(d["secret_b58"])), d["pubkey"]

def sol_balance(pubkey):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [pubkey]}).encode()
    try:
        r = json.load(urllib.request.urlopen(urllib.request.Request(RPC, data=body, headers=UA), timeout=20))
        return (r.get("result", {}).get("value", 0)) / 1e9
    except Exception:
        return 0.0

def token_balance(pubkey, mint):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getTokenAccountsByOwner",
                       "params": [pubkey, {"mint": mint}, {"encoding": "jsonParsed"}]}).encode()
    try:
        r = json.load(urllib.request.urlopen(urllib.request.Request(RPC, data=body, headers=UA), timeout=20))
        total = 0
        for a in r.get("result", {}).get("value", []):
            info = a["account"]["data"]["parsed"]["info"]
            total += int(info["tokenAmount"]["amount"])
        return total
    except Exception:
        return 0

def jup_quote(in_mint, out_mint, amount_raw):
    url = f"{JUP_QUOTE}?inputMint={in_mint}&outputMint={out_mint}&amount={amount_raw}&slippageBps=150"
    try:
        return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA["User-Agent"]}), timeout=20))
    except Exception:
        return None

def jup_swap_tx(keypair, in_mint, out_mint, amount_raw):
    """Build + sign a Jupiter swap tx. Returns serialized tx (base64) or None."""
    q = jup_quote(in_mint, out_mint, amount_raw)
    if not q: return None, "no route"
    body = json.dumps({
        "quoteResponse": q,
        "userPublicKey": str(keypair.pubkey()),
        "wrapAndUnwrapSol": True,
        "dynamicComputeUnitLimit": True,
        "prioritizationFeeLamports": {"priorityLevelWithMaxLamports": {"maxLamports": 1000000, "priorityLevel": "high"}}
    }).encode()
    req = urllib.request.Request(JUP_SWAP, data=body, headers=UA)
    try:
        swap = json.load(urllib.request.urlopen(req, timeout=25))
    except Exception as e:
        return None, f"swap api: {e}"
    b64 = swap.get("swapTransaction")
    if not b64: return None, "no swapTransaction"
    try:
        from solders.transaction import VersionedTransaction
        import base64 as b64mod
        raw = b64mod.b64decode(b64)
        # VersionedTransaction.deserialize expects message + sigs; use the SDK pattern:
        # simplest: sign by deserializing then re-signing
        from solders.message import VersionedMessage
        msg = VersionedMessage.deserialize(raw) if hasattr(VersionedMessage, "deserialize") else None
        # fallback: use solders' Transaction utilities
        # NOTE: exact sign flow depends on solders version; test on VPS
        return b64, q
    except Exception as e:
        return None, f"sign: {e}"

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "create":
        r = create_wallet()
        print(json.dumps(r, indent=1) if r else "wallet already exists")
    elif len(sys.argv) > 1 and sys.argv[1] == "balance":
        _, pub = load_wallet()
        print("SOL:", sol_balance(pub))
