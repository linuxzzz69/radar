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

def get_json(url):
    """HTTP GET -> parsed JSON. (Was previously called-but-undefined here,
    silently killing every price fetch in this module.)"""
    return json.load(urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": UA["User-Agent"]}), timeout=25))

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
    for url in (RPC, "https://solana-rpc.publicnode.com"):
        try:
            body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [pubkey]}).encode()
            r = json.load(urllib.request.urlopen(urllib.request.Request(url, data=body, headers=UA), timeout=20))
            return (r.get("result", {}).get("value", 0)) / 1e9
        except Exception:
            continue
    return 0.0

def token_balance(pubkey, mint):
    """RAW on-chain amount. 0 = confirmed empty. None = both RPCs failed
    (callers must NOT treat None as 'holds nothing')."""
    for url in (RPC, "https://solana-rpc.publicnode.com"):
        try:
            body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getTokenAccountsByOwner",
                               "params": [pubkey, {"mint": mint}, {"encoding": "jsonParsed"}]}).encode()
            r = json.load(urllib.request.urlopen(urllib.request.Request(url, data=body, headers=UA), timeout=20))
            total = 0
            for a in r.get("result", {}).get("value", []):
                info = a["account"]["data"]["parsed"]["info"]
                total += int(info["tokenAmount"]["amount"])
            return total
        except Exception:
            continue
    return None

def token_amount_ui(pubkey, mint):
    """(ui_amount, decimals) as shown in wallets.
    (0, 0) = account checked, genuinely empty.
    (None, None) = both RPCs failed — caller must NOT treat this as 'no position'."""
    for url in (RPC, "https://solana-rpc.publicnode.com"):
        try:
            body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getTokenAccountsByOwner",
                               "params": [pubkey, {"mint": mint}, {"encoding": "jsonParsed"}]}).encode()
            r = json.load(urllib.request.urlopen(urllib.request.Request(url, data=body, headers=UA), timeout=20))
            ui, dec = 0.0, 0
            for a in r.get("result", {}).get("value", []):
                ta = a["account"]["data"]["parsed"]["info"]["tokenAmount"]
                ui += float(ta.get("uiAmount") or 0)
                dec = int(ta.get("decimals") or 0)
            return ui, dec
        except Exception:
            continue
    return None, None

def jup_price_usd(mint):
    """Jupiter price API fallback (USD). v3 format: {"<mint>": {"usdPrice": ...}}"""
    try:
        d = get_json(f"https://lite-api.jup.ag/price/v3?ids={mint}")
        if not isinstance(d, dict):
            return 0.0
        info = d.get(mint) or (d.get("data") or {}).get(mint) or {}
        p = info.get("usdPrice") or info.get("price")
        return float(p) if p else 0.0
    except Exception:
        return 0.0

def token_price_usd(mint):
    """DexScreener best-pair price, Jupiter fallback."""
    try:
        dd = get_json(f"https://api.dexscreener.com/latest/dex/tokens/{mint}")
        ps = dd.get("pairs") or []
        best = max(ps, key=lambda x: (x.get("liquidity") or {}).get("usd", 0)) if ps else None
        if best and best.get("priceUsd"):
            return float(best["priceUsd"])
    except Exception:
        pass
    return jup_price_usd(mint)

def sol_price_usd():
    try:
        dd = get_json("https://api.dexscreener.com/latest/dex/tokens/So11111111111111111111111111111111111111112")
        ps = dd.get("pairs") or []
        best = max(ps, key=lambda x: (x.get("liquidity") or {}).get("usd", 0)) if ps else None
        if best and best.get("priceUsd"):
            return float(best["priceUsd"])
    except Exception:
        pass
    return jup_price_usd("So11111111111111111111111111111111111111112")

SLIP_LADDER = [150, 500, 1000, 2000]  # bps: 1.5% -> 5% -> 10% -> 20% (hot launches move fast)

def trade_cfg():
    """Live-reload trading settings from watch_config.json 'trading' block.
    priority: low|medium|high  |  max_priority_lamports: cap for the priority fee."""
    d = load(os.path.join(BASE, "watch_config.json"), {}) or {}
    t = d.get("trading") or {}
    return {
        "priority": t.get("priority", "medium"),
        "max_priority_lamports": int(t.get("max_priority_lamports", 300000)),
    }


def jup_quote_raw(in_mint, out_mint, amount_raw, direct_only=False, slippage_bps=150):
    """(quote, err). Distinguishes: 'no route found' (API answered, nothing to route)
    from transient API failures (502/503/timeout) which carry the real message."""
    url = f"{JUP_QUOTE}?inputMint={in_mint}&outputMint={out_mint}&amount={amount_raw}&slippageBps={slippage_bps}"
    if direct_only:
        url += "&onlyDirectRoutes=true"
    try:
        return json.load(urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": UA["User-Agent"]}), timeout=20)), None
    except urllib.error.HTTPError as e:
        try:
            msg = e.read().decode()[:300]
        except Exception:
            msg = str(e)
        if "route" in msg.lower():
            return None, "no route found (no sellable liquidity on any DEX)"
        return None, f"quote api {e.code}: {msg[:140]}"
    except Exception as e:
        return None, f"quote api: {e}"

def jup_quote(in_mint, out_mint, amount_raw, direct_only=False, slippage_bps=150):
    return jup_quote_raw(in_mint, out_mint, amount_raw,
                         direct_only=direct_only, slippage_bps=slippage_bps)[0]

def jup_swap_tx(keypair, in_mint, out_mint, amount_raw, direct_only=False, slippage_bps=150):
    """Build a Jupiter swap tx and return it UNSIGNED-ready (bot signs)."""
    q, qerr = jup_quote_raw(in_mint, out_mint, amount_raw,
                            direct_only=direct_only, slippage_bps=slippage_bps)
    if not q: return None, qerr or "no route found"
    tc = trade_cfg()
    body = json.dumps({
        "quoteResponse": q,
        "userPublicKey": str(keypair.pubkey()),
        "wrapAndUnwrapSol": True,
        "dynamicComputeUnitLimit": True,
        "prioritizationFeeLamports": {"priorityLevelWithMaxLamports": {
            "maxLamports": tc["max_priority_lamports"],
            "priorityLevel": tc["priority"]}}
    }).encode()
    req = urllib.request.Request(JUP_SWAP, data=body, headers=UA)
    try:
        swap = json.load(urllib.request.urlopen(req, timeout=25))
    except Exception as e:
        return None, f"swap api: {e}"
    b64 = swap.get("swapTransaction")
    if not b64: return None, "no swapTransaction returned"
    import base64 as _b
    if len(_b.b64decode(b64)) > 1232:
        return None, "tx too large for network packet (1232B) — needs direct route"
    return b64, q

def sign_and_send(keypair, swap_b64):
    """Sign the Jupiter swapTransaction with the bot keypair, send, return signature."""
    import base64 as b64mod
    from solders.transaction import VersionedTransaction
    raw = b64mod.b64decode(swap_b64)
    vt = VersionedTransaction.from_bytes(raw)
    # solders 0.29: the constructor takes keypairs and signs internally
    signed = VersionedTransaction(vt.message, [keypair])
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

def confirm_tx(sig, timeout=45):
    """Poll getSignatureStatuses until the tx lands.
    Returns (True, None) confirmed ok | (False, err) failed on-chain |
    (None, 'unconfirmed') not seen before timeout (do NOT retry those)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for url in (RPC, "https://solana-rpc.publicnode.com"):
            try:
                body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getSignatureStatuses",
                                   "params": [[sig], {"searchTransactionHistory": True}]}).encode()
                r = json.load(urllib.request.urlopen(urllib.request.Request(url, data=body, headers=UA), timeout=20))
                val = (((r.get("result") or {}).get("value") or [None]) or [None])[0]
                if val is None:
                    break
                if val.get("err"):
                    return False, str(val.get("err"))
                if val.get("confirmationStatus"):
                    return True, None
            except Exception:
                continue
        time.sleep(3)
    return None, "unconfirmed"


def jup_swap_with_retry(keypair, in_mint, out_mint, amount_raw, retries=5):
    """Full swap with Jupiter API retry (lite-api flaps), direct-route fallback
    for oversized txs, and slippage escalation (1.5% -> 5% -> 10%) for fast movers."""
    last = None
    direct = False
    slip_idx = 0
    for i in range(retries):
        slip = SLIP_LADDER[min(slip_idx, len(SLIP_LADDER) - 1)]
        b64, err = jup_swap_tx(keypair, in_mint, out_mint, amount_raw,
                               direct_only=direct, slippage_bps=slip)
        if b64:
            sig, serr = sign_and_send(keypair, b64)
            if sig:
                ok, cerr = confirm_tx(sig)
                if ok is True:
                    return sig, None
                if ok is False:
                    # tx landed and FAILED on-chain (funds did NOT move) — safe to retry
                    last = f"tx failed on-chain: {cerr}"
                    s = cerr.lower()
                    if ("custom" in s or "slippage" in s or "error" in s) and slip_idx < len(SLIP_LADDER) - 1:
                        slip_idx += 1
                        continue
                    return None, last
                # timeout: tx may still land — never retry (double-buy risk)
                return sig, (f"submitted but not confirmed yet — check "
                             f"https://solscan.io/tx/{sig} and /balance before retrying")
            last = serr
            s = str(serr)
            if "too large" in s.lower() and not direct:
                direct = True
                continue
            if ("custom program error" in s or "slippage" in s.lower()
                    and slip_idx < len(SLIP_LADDER) - 1):
                slip_idx += 1
                continue
            return sig, serr
        last = err
        s = str(err)
        if "too large" in s.lower() and not direct:
            direct = True
            continue
        if ("custom program error" in s or "slippage" in s.lower()
                and slip_idx < len(SLIP_LADDER) - 1):
            slip_idx += 1
            continue
        if "502" in s or "503" in s or "unavailable" in s.lower():
            time.sleep(3 * (i + 1))
            continue
        break
    return None, last

def do_buy(out_mint, sol_amount):
    kp, pub = load_wallet()
    bal = sol_balance(pub)
    # rent for output-token ATA ~0.002 + priority-fee headroom ~0.002 + safety
    fee_buf = 0.005 if sol_amount < 0.05 else 0.01
    if bal < sol_amount + fee_buf:
        return None, f"insufficient SOL: {bal:.4f} (need {sol_amount} + ~{fee_buf} fees/rent)"
    return jup_swap_with_retry(kp, SOL_MINT, out_mint, int(sol_amount * 1e9))

def do_sell(mint, pct):
    kp, pub = load_wallet()
    total = token_balance(pub, mint)
    if total is None:
        return None, "balance check failed (RPC busy) — tap Sell again"
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
        # tokens are UI (wallet-display) units — keep fractional, delete on dust
        d[mint]["tokens"] = d[mint]["tokens"] * (100 - pct) / 100
        if d[mint]["tokens"] <= 1e-6:
            del d[mint]
        save_positions(d)

def reconcile_positions():
    """Chain is truth: add wallet holdings missing from the book (SPL + Token-2022).
    Survives state wipes, manual wallet usage, anything. Returns list of added mints."""
    try:
        _, pub = load_wallet()
        mints = {}
        for prog in ("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",   # SPL Token
                     "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"):  # Token-2022
            for url in (RPC, "https://solana-rpc.publicnode.com"):
                try:
                    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getTokenAccountsByOwner",
                                       "params": [pub, {"programId": prog}, {"encoding": "jsonParsed"}]}).encode()
                    r = json.load(urllib.request.urlopen(urllib.request.Request(url, data=body, headers=UA), timeout=20))
                    for a in r.get("result", {}).get("value", []):
                        info = a["account"]["data"]["parsed"]["info"]
                        ui = float(info["tokenAmount"].get("uiAmount") or 0)
                        if ui > 0 and info.get("mint") != SOL_MINT:
                            mints[info["mint"]] = ui
                    break
                except Exception:
                    continue
        d = load_positions()
        added = []
        dirty = False
        for mint, ui in mints.items():
            p = d.get(mint)
            needs_add = not p or p.get("tokens", 0) <= 0
            needs_sym = (not needs_add) and p.get("symbol", "?") == "?"
            if needs_add or needs_sym:
                sym = (p or {}).get("symbol") or "?"
                if sym == "?":
                    try:
                        dd = get_json(f"https://api.dexscreener.com/latest/dex/tokens/{mint}")
                        ps = dd.get("pairs") or []
                        best = max(ps, key=lambda x: (x.get("liquidity") or {}).get("usd", 0)) if ps else None
                        sym = ((best.get("baseToken") or {}).get("symbol") or "?") if best else "?"
                    except Exception:
                        sym = "?"
                old_sol_in = (p or {}).get("sol_in", 0.0)
                old_tokens = (p or {}).get("tokens", ui) if p else ui
                d[mint] = {"symbol": sym, "sol_in": old_sol_in, "tokens": old_tokens}
                dirty = True
                if needs_add:
                    added.append(mint)
        if dirty:
            save_positions(d)
        return added
    except Exception:
        return []


def record_entry_meta(mint, mcap, price):
    """Store entry mcap/price on the position (first buy wins)."""
    try:
        d = load_positions()
        if mint in d:
            if mcap: d[mint].setdefault("entry_mcap", float(mcap))
            if price: d[mint].setdefault("entry_price", float(price))
            save_positions(d)
    except Exception:
        pass


def positions_overview():
    """Build the Positions Overview card with live prices."""
    reconcile_positions()  # chain is truth: pull in any holdings missing from the book
    d = load_positions()
    _, pub = load_wallet()
    lines = []
    net_sol = sol_balance(pub)
    sp = sol_price_usd()
    for mint, p in list(d.items()):
        if p.get("tokens", 0) <= 0:
            # post-buy unresolved record: try resolving from the live chain
            try:
                ui, _dec = token_amount_ui(pub, mint)
                if ui is None:
                    # RPC failed — show the position as pending instead of hiding it
                    lines.append(f"/{p.get('symbol', '?')} ⏳ (balance check busy — retry /positions)")
                    continue
                if ui > 0:
                    p["tokens"] = ui
                    save_positions(d)
                else:
                    continue  # confirmed: wallet holds none
            except Exception:
                continue
        if p["tokens"] <= 0: continue
        # live price via DexScreener
        try:
            dd = get_json(f"https://api.dexscreener.com/latest/dex/tokens/{mint}")
            ps = dd.get("pairs") or []
            best = max(ps, key=lambda x: (x.get("liquidity") or {}).get("usd", 0)) if ps else None
            price_usd = float(best["priceUsd"]) if best and best.get("priceUsd") else 0
            sym = best["baseToken"]["symbol"] if best else p["symbol"]
        except Exception:
            price_usd, sym = 0, p["symbol"]
        usd = p["tokens"] * price_usd
        val_sol = (usd / sp) if (sp and usd) else 0
        pnl_sol = val_sol - p["sol_in"]
        pnl_pct = (pnl_sol / p["sol_in"] * 100) if p["sol_in"] else 0
        emoji = "🟢" if pnl_pct >= 0 else "🔴"
        lines.append(
            f"/{sym} {emoji}\n"
            f"PnL: {pnl_pct:+.1f}% / {pnl_sol:+.4f} SOL\n"
            f"Value: ${usd:.2f} / {val_sol:.4f} SOL\n"
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

def set_rule(mint, kind, pct, sell_pct=None):
    d = load_sltp()
    d.setdefault(mint, {})[kind] = pct
    if kind == "tp":
        if sell_pct is not None and 0 < sell_pct < 100:
            d[mint]["tp_sell"] = sell_pct
        else:
            d[mint].pop("tp_sell", None)
    save_sltp(d)

def clear_rule(mint, *kinds):
    d = load_sltp()
    if mint in d:
        for k in kinds:
            d[mint].pop(k, None)
        if not d[mint]:
            d.pop(mint)
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
    """Return (symbol, value_sol, pnl_sol, pnl_pct, tokens) for an open position.
    tokens is in UI (wallet-display) units."""
    d = load_positions()
    p = d.get(mint)
    if not p: return None
    # right after a buy, tokens is stored as 0 — resolve from the live chain balance
    if p.get("tokens", 0) <= 0:
        try:
            _, pub = load_wallet()
            ui, _dec = token_amount_ui(pub, mint)
            if ui is None:
                return None  # RPC failed — no fake data, engine skips this cycle
            if ui > 0:
                p["tokens"] = ui
                d[mint] = p
                save_positions(d)
        except Exception:
            pass
    if p.get("tokens", 0) <= 0: return None
    price_usd = token_price_usd(mint)
    if not price_usd:
        return None  # no live price from either source — never compute a fake PnL
    sp = sol_price_usd()
    if not sp:
        return None
    sym = p.get("symbol") or "?"
    usd = p["tokens"] * price_usd
    val_sol = usd / sp
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

def load(p, default):
    try:
        with open(p) as f: return json.load(f)
    except Exception:
        return default

def log_trade(action, mint, symbol, sol_amount, sig=None, err=None):
    """Audit trail: every auto-action is logged forever."""
    d = load(HIST_PATH, {})
    d.setdefault("trades", []).append({
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

def clear_all_limits():
    """Cancel every limit buy/sell rule (price and mcap modes). TP/SL/trail untouched."""
    d = load_sltp()
    cleared = []
    for mint, rules in list(d.items()):
        if not any(k in rules for k in ("buy_limit", "sell_limit", "buy_limit_mc", "sell_limit_mc")):
            continue
        for k in ("buy_limit", "buy_limit_sol", "buy_limit_att", "buy_limit_mc",
                   "sell_limit", "sell_limit_pct", "sell_limit_att", "sell_limit_mc"):
            rules.pop(k, None)
        if not rules:
            d.pop(mint)
        cleared.append(mint)
    if cleared:
        save_sltp(d)
    return cleared


def mcap_usd(mint):
    """Live market cap from DexScreener's best-pair data (what gmgn shows)."""
    try:
        dd = get_json(f"https://api.dexscreener.com/latest/dex/tokens/{mint}")
        ps = dd.get("pairs") or []
        best = max(ps, key=lambda x: (x.get("liquidity") or {}).get("usd", 0)) if ps else None
        if best and best.get("marketCap"):
            return float(best["marketCap"])
    except Exception:
        pass
    return 0.0


def trade_volume():
    """(n_buys, sol_bought, n_sells, n_blocked) from the persistent audit log."""
    d = load(HIST_PATH, {"trades": []})
    trades = d.get("trades", [])
    buys = [t for t in trades if t.get("action") == "buy" and not t.get("error")]
    sells = [t for t in trades if t.get("action") == "sell" and not t.get("error")]
    blocked = [t for t in trades if t.get("action") == "buy_blocked"]
    return (len(buys), sum(t.get("sol", 0) or 0 for t in buys),
            len(sells), len(blocked))


def hardened_sell(mint, symbol, pct):
    if is_denied(mint=mint):
        return None, "mint is deny-listed"
    sig, err = do_sell(mint, pct)
    record_sell(mint, pct)
    log_trade("sell", mint, symbol, pct, sig=sig, err=err)
    return sig, err
