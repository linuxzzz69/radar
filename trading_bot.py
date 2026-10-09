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
    """Build a Jupiter swap tx and return it UNSIGNED-ready (bot signs)."""
    q = jup_quote(in_mint, out_mint, amount_raw)
    if not q: return None, "no route found"
    body = json.dumps({
        "quoteResponse": q,
        "userPublicKey": str(keypair.pubkey()),
        "wrapAndUnwrapSol": True,
        "dynamicComputeUnitLimit": True,
        "prioritizationFeeLamports": {"priorityLevelWithMaxLamports": {"maxLamports": 2000000, "priorityLevel": "high"}}
    }).encode()
    req = urllib.request.Request(JUP_SWAP, data=body, headers=UA)
    try:
        swap = json.load(urllib.request.urlopen(req, timeout=25))
    except Exception as e:
        return None, f"swap api: {e}"
    b64 = swap.get("swapTransaction")
    if not b64: return None, "no swapTransaction returned"
    return b64, q

def sign_and_send(keypair, swap_b64):
    """Sign the Jupiter swapTransaction with the bot keypair, send, return signature."""
    import base64 as b64mod
    from solders.transaction import VersionedTransaction
    raw = b64mod.b64decode(swap_b64)
    vt = VersionedTransaction.from_bytes(raw)
    # sign: keypair.sign_message(vt.message) -> Signature, then reassemble
    sig = keypair.sign_message(vt.message)
    signed = VersionedTransaction(vt.message, [sig])
    # send the signed tx
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "sendTransaction",
                       "params": [b64mod.b64encode(bytes(signed)).decode(),
                                  {"encoding": "base64", "skipPreflight": False, "maxRetries": 3}]}).encode()
    for url in [RPC, "https://solana-rpc.publicnode.com"]:
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(url, data=body, headers=UA), timeout=25))
            if "error" in r:
                last = r["error"]; continue
            return r.get("result"), None
        except Exception as e:
            last = str(e); continue
    return None, str(last)

def jup_swap_with_retry(keypair, in_mint, out_mint, amount_raw, retries=3):
    """Full swap with Jupiter API retry (lite-api flaps 502/503)."""
    last = None
    for i in range(retries):
        b64, err = jup_swap_tx(keypair, in_mint, out_mint, amount_raw)
        if b64:
            return sign_and_send(keypair, b64)
        last = err
        if err and ("502" in str(err) or "503" in str(err) or "unavailable" in str(err).lower()):
            time.sleep(3 * (i + 1)); continue
        break
    return None, last

def do_buy(out_mint, sol_amount):
    kp, pub = load_wallet()
    bal = sol_balance(pub)
    if bal < sol_amount + 0.01:
        return None, f"insufficient SOL: {bal:.3f} (need {sol_amount} + fees)"
    return jup_swap_with_retry(kp, SOL_MINT, out_mint, int(sol_amount * 1e9))

def do_sell(mint, pct):
    kp, pub = load_wallet()
    total = token_balance(pub, mint)
    if total <= 0: return None, "no token balance to sell"
    raw = int(total * pct / 100)
    return jup_swap_with_retry(kp, mint, SOL_MINT, raw)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "create":
        r = create_wallet()
        print(json.dumps(r, indent=1) if r else "wallet already exists")
    elif len(sys.argv) > 1 and sys.argv[1] == "balance":
        _, pub = load_wallet()
        print("SOL:", sol_balance(pub))


# ---------------- position tracking ----------------

POS_PATH = os.path.join(BASE, ".bot_positions.json")

def load_positions():
    try:
        with open(POS_PATH) as f: return json.load(f)
    except Exception:
        return {}

def save_positions(d):
    with open(POS_PATH, "w") as f: json.dump(d, f, indent=1)

def record_buy(mint, symbol, sol_spent, tokens):
    d = load_positions()
    p = d.setdefault(mint, {"symbol": symbol, "sol_in": 0.0, "tokens": 0})
    p["sol_in"] += sol_spent
    p["tokens"] += tokens
    save_positions(d)

def record_sell(mint, pct):
    d = load_positions()
    if mint in d:
        d[mint]["tokens"] = int(d[mint]["tokens"] * (100 - pct) / 100)
        if d[mint]["tokens"] <= 0:
            del d[mint]
        save_positions(d)

def positions_overview():
    """Build the Positions Overview card with live prices."""
    d = load_positions()
    _, pub = load_wallet()
    lines = []
    net_sol = sol_balance(pub)
    for mint, p in d.items():
        if p["tokens"] <= 0: continue
        # live price via DexScreener
        try:
            dd = get_json(f"https://api.dexscreener.com/latest/dex/tokens/{mint}")
            ps = dd.get("pairs") or []
            best = max(ps, key=lambda x: (x.get("liquidity") or {}).get("usd", 0)) if ps else None
            price_usd = float(best["priceUsd"]) if best and best.get("priceUsd") else 0
            val_sol = (p["tokens"] * price_usd) / 1e9 if price_usd else 0
            sym = best["baseToken"]["symbol"] if best else p["symbol"]
        except Exception:
            price_usd, val_sol, sym = 0, 0, p["symbol"]
        pnl_sol = val_sol - p["sol_in"]
        pnl_pct = (pnl_sol / p["sol_in"] * 100) if p["sol_in"] else 0
        emoji = "🟢" if pnl_pct >= 0 else "🔴"
        lines.append(
            f"/{sym} {emoji}\n"
            f"PnL: {pnl_pct:+.1f}% / {pnl_sol:+.4f} SOL\n"
            f"Value: ${(p['tokens']*price_usd):.2f} / {val_sol:.4f} SOL\n"
            f"Entry: {p['sol_in']:.4f} SOL"
        )
        net_sol += val_sol
    return lines, net_sol


# ---------------- live PnL + SL/TP engine ----------------

SLTP_PATH = os.path.join(BASE, ".bot_sltp.json")
CARD_PATH = os.path.join(BASE, ".bot_cards.json")  # mint -> (chat_id, message_id)

def load_sltp():
    try:
        with open(SLTP_PATH) as f: return json.load(f)
    except Exception:
        return {}

def save_sltp(d):
    with open(SLTP_PATH, "w") as f: json.dump(d, f, indent=1)

def set_rule(mint, kind, pct):
    d = load_sltp()
    d.setdefault(mint, {})[kind] = pct
    save_sltp(d)

def get_rules(mint):
    return load_sltp().get(mint, {})

def save_card(mint, chat_id, msg_id):
    d = load_card_all()
    d[mint] = {"chat": chat_id, "msg": msg_id}
    with open(CARD_PATH, "w") as f:
        json.dump(d, f, indent=1)

def load_card_all():
    try:
        with open(CARD_PATH) as f: return json.load(f)
    except Exception:
        return {}

def load_card(mint):
    return load_card_all().get(mint)

def position_pnl(mint):
    """Return (symbol, value_sol, pnl_sol, pnl_pct, tokens) for an open position."""
    d = load_positions()
    p = d.get(mint)
    if not p or p["tokens"] <= 0: return None
    try:
        dd = get_json(f"https://api.dexscreener.com/latest/dex/tokens/{mint}")
        ps = dd.get("pairs") or []
        best = max(ps, key=lambda x: (x.get("liquidity") or {}).get("usd", 0)) if ps else None
        price_usd = float(best["priceUsd"]) if best and best.get("priceUsd") else 0
        sym = (best["baseToken"]["symbol"] if best else p["symbol"]) or "?"
    except Exception:
        price_usd, sym = 0, p["symbol"]
    val_sol = (p["tokens"] * price_usd) / 1e9
    pnl_sol = val_sol - p["sol_in"]
    pnl_pct = (pnl_sol / p["sol_in"] * 100) if p["sol_in"] else 0
    return sym, val_sol, pnl_sol, pnl_pct, p["tokens"]


# ---------------- trade hardening ----------------

DENY_PATH = os.path.join(BASE, ".denylist.json")   # mints/wallets we never trade
HIST_PATH = os.path.join(BASE, ".trade_history.json")

def load_deny():
    try:
        with open(DENY_PATH) as f: return json.load(f)
    except Exception:
        return {"mints": [], "wallets": []}

def is_denied(mint=None, wallet=None):
    d = load_deny()
    if mint and mint in d.get("mints", []): return True
    if wallet and wallet in d.get("wallets", []): return True
    return False

def log_trade(action, mint, symbol, sol_amount, sig=None, err=None):
    """Audit trail: every auto-action is logged forever."""
    d = load(HIST_PATH, {"trades": []})
    d["trades"].append({
        "ts": time.time(), "action": action, "mint": mint, "symbol": symbol,
        "sol": sol_amount, "sig": sig, "error": err
    })
    with open(HIST_PATH, "w") as f: json.dump(d, f, indent=1)

def daily_spend():
    """Total SOL spent on buys in the last 24h (guardrail)."""
    d = load(HIST_PATH, {"trades": []})
    day_ago = time.time() - 86400
    total = sum(t.get("sol", 0) for t in d.get("trades", [])
                if t.get("ts", 0) > day_ago and t.get("action") == "buy" and not t.get("error"))
    return total

def hardened_buy(mint, symbol, sol_amount, max_daily=0.5):
    """do_buy with all guardrails applied. Returns (sig, err)."""
    if is_denied(mint=mint):
        log_trade("buy_blocked", mint, symbol, sol_amount, err="deny-listed")
        return None, "mint is deny-listed"
    spent = daily_spend()
    if spent + sol_amount > max_daily:
        log_trade("buy_blocked", mint, symbol, sol_amount,
                  err=f"daily cap: {spent:.2f} SOL spent, cap {max_daily}")
        return None, f"daily spend cap hit ({spent:.2f}/{max_daily} SOL)"
    sig, err = do_buy(mint, sol_amount)
    if not err:
        record_buy(mint, symbol, sol_amount, 0)  # tokens resolved from tx on next /positions refresh
    log_trade("buy", mint, symbol, sol_amount, sig=sig, err=err)
    return sig, err

def hardened_sell(mint, symbol, pct):
    if is_denied(mint=mint):
        return None, "mint is deny-listed"
    sig, err = do_sell(mint, pct)
    record_sell(mint, pct)
    log_trade("sell", mint, symbol, pct, sig=sig, err=err)
    return sig, err
