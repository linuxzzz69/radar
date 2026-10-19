#!/usr/bin/env python3
"""
toll_watch.py - Earliness machine: alert when a high-fee Meteora DLMM pool
is seeded on a young token. Toll booths get built before crowds arrive.
The +1074% runner is downstream. The pool placement is upstream.

Signal chain (from dlmm-notes.md / farm_pl.py):
  farm seeds DLMM side pool at 100-300 bps  ->  run starts  ->  volume
  ->  fees print  ->  Discord talks  ->  you were late.
This alert fires at step 1.

Fires when: new Meteora DLMM pair, baseFeeBps >= MIN_FEE (default 100),
token launched <= MAX_TOKEN_AGE_H (default 48h). Alert includes the farm
fingerprint: churn ratio, symmetry, mcap, main-pool liquidity.

Usage:
  python3 toll_watch.py              # loop forever (poll every 600s)
  python3 toll_watch.py --once       # single pass (cron mode)
  python3 toll_watch.py --dry-run    # print alerts, no telegram

State: .toll_state.json (seen pairs + recent token window)
Config: watch_config.json (telegram creds, same as watcher.py)
Fees: dlmm_fee.js (Meteora LbPair via @meteora-ag/dlmm SDK)
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(BASE, "watch_config.json")
STATE_PATH = os.path.join(BASE, ".toll_state.json")
UA = {"User-Agent": "Mozilla/5.0"}

POLL_SEC = 600
TOKEN_WINDOW_H = 48
MIN_FEE_BPS = 100.0
LOUD_FEE_BPS = 200.0
MAX_TOKENS = 40


def get_json(url):
    req = urllib.request.Request(url, headers=UA)
    return json.load(urllib.request.urlopen(req, timeout=25))


def tg_send(token, chat, text):
    import urllib.parse
    data = urllib.parse.urlencode({"chat_id": chat, "text": text, "parse_mode": "HTML",
                                   "disable_web_page_preview": "true"}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data), timeout=15)
    except Exception as e:
        print("tg send failed:", e)


def load_state():
    try:
        return json.load(open(STATE_PATH))
    except Exception:
        return {"seen_pairs": {}, "recent_tokens": {}}


def save_state(st):
    json.dump(st, open(STATE_PATH, "w"), indent=1)


def dlmm_fee(pair):
    try:
        out = subprocess.run(["node", os.path.join(BASE, "dlmm_fee.js"), pair],
                              capture_output=True, text=True, timeout=90)
        rows = json.loads(out.stdout)
        return rows[0] if rows and rows[0].get("ok") else None
    except Exception:
        return None


def token_fingerprint(pairs):
    """Farm fingerprint from the same DexScreener pull: churn ratio + symmetry."""
    main = [p for p in pairs if p.get("dexId") in ("pumpfun", "pumpswap")]
    main = max(main, key=lambda p: (p.get("liquidity") or {}).get("usd", 0)) if main else None
    if not main:
        return {}
    v24 = main["volume"].get("h24") or 0
    tx = main["txns"].get("h24") or {}
    b, s = tx.get("buys", 0), tx.get("sells", 0)
    mcap = main.get("marketCap") or main.get("fdv") or 0
    sig = round(min(b, s) / max(b, s), 2) if b and s else 0.0
    return {"mcap": mcap, "churn_ratio": round(v24 / mcap, 1) if mcap else 0,
            "symmetry": sig, "main_liq": (main.get("liquidity") or {}).get("usd", 0),
            "v24": v24, "symbol": main["baseToken"].get("symbol", "?")}


def money(x):
    return f"${x:,.0f}"


def alert_text(fp, fee, fee_row, sp, mint):
    loud = fee >= LOUD_FEE_BPS
    head = "\U0001F6A8 <b>NEW TOLL BOOTH SEEDED</b>" if loud else "\U0001F514 <b>High-fee DLMM pool seeded</b>"
    churn = f"{fp.get('churn_ratio', 0)}x mcap" if fp.get("churn_ratio") else "n/a"
    sym = fp.get("symmetry")
    sym_txt = f"{sym:.2f} (1:1 = churn)" if sym else "n/a"
    mcap = money(fp["mcap"]) if fp.get("mcap") else "n/a"
    return (f"{head}\n"
            f"\U0001F4B0 <b>{fp.get('symbol', '?')}</b>  fee {fee:.0f} bps  binStep {fee_row.get('binStep', '?')}\n"
            f"\U0001F3EA mcap {mcap}  main liq {money(fp.get('main_liq', 0))}\n"
            f"\U0001F4CA h24 vol {money(fp.get('v24', 0))}  churn {churn}\n"
            f"\U0001F9EE symmetry {sym_txt}\n"
            f"CA: <code>{mint}</code>\n"
            f"pair: <code>{sp['pairAddress']}</code>\n"
            f"https://dexscreener.com/solana/{sp['pairAddress']}")


def one_pass(cfg, dry):
    st = load_state()
    now = time.time()
    tg = cfg.get("telegram", {})
    alerts = 0

    fresh_tokens = []
    try:
        profs = get_json("https://api.dexscreener.com/token-profiles/latest/v1")
        for t in profs:
            if t.get("chainId") != "solana":
                continue
            m = t.get("tokenAddress")
            if m and m not in st["recent_tokens"] and m not in fresh_tokens:
                fresh_tokens.append(m)
    except Exception as e:
        print("profiles fetch failed:", e)

    for m in fresh_tokens:
        st["recent_tokens"][m] = now

    tokens = [(m, ts) for m, ts in st["recent_tokens"].items() if now - ts <= TOKEN_WINDOW_H * 3600]
    tokens.sort(key=lambda kv: kv[1])
    tokens = tokens[-MAX_TOKENS:]
    st["recent_tokens"] = dict(tokens)

    for mint, _ in tokens:
        try:
            pairs = get_json(f"https://api.dexscreener.com/latest/dex/tokens/{mint}").get("pairs") or []
        except Exception:
            continue
        for p in pairs:
            if p.get("dexId") != "meteora" or "DLMM" not in (p.get("labels") or []):
                continue
            pair = p["pairAddress"]
            if pair in st["seen_pairs"]:
                continue
            fee = dlmm_fee(pair)
            if fee is None:
                st["seen_pairs"].setdefault(pair, {"fails": 0})
                st["seen_pairs"][pair]["fails"] = st["seen_pairs"][pair].get("fails", 0) + 1
                if st["seen_pairs"][pair]["fails"] >= 3:
                    print(f"fee fetch failed 3x, dropping pair {pair[:16]}..")
                else:
                    del st["seen_pairs"][pair]
                continue
            st["seen_pairs"][pair] = {"feeBps": fee.get("baseFeeBps"), "ts": now}
            if len(st["seen_pairs"]) > 500:
                st["seen_pairs"] = dict(sorted(st["seen_pairs"].items(),
                                               key=lambda kv: -kv[1].get("ts", 0))[:300])
            f = fee.get("baseFeeBps") or 0
            if f >= MIN_FEE_BPS:
                fp = token_fingerprint(pairs)
                fp["symbol"] = p["baseToken"].get("symbol", fp.get("symbol", "?"))
                txt = alert_text(fp, f, fee, p, mint)
                if dry:
                    print("--- DRY RUN ALERT ---")
                    print(txt)
                else:
                    tg_send(tg.get("token"), tg.get("chat_id"), txt)
                    print(f"alert: {fp.get('symbol')} fee={f}bps pair={pair[:16]}..")
                alerts += 1
        time.sleep(0.4)

    save_state(st)
    return alerts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try:
        cfg = json.load(open(CFG_PATH))
    except Exception as e:
        sys.exit(f"config load failed: {e}")

    if args.once:
        n = one_pass(cfg, args.dry_run)
        print(f"pass complete, {n} alert(s)")
        return
    print("toll_watch running. poll every", POLL_SEC, "s")
    while True:
        try:
            one_pass(cfg, args.dry_run)
        except KeyboardInterrupt:
            sys.exit(0)
        except Exception as e:
            print("pass error:", e)
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
