#!/usr/bin/env python3
"""
fresh_battery.py - Fresh DBC launch battery
Finds new Solana launches, flags Meteora DBC ones, and runs the safety scanner
on each DBC candidate. Outputs a ranked table.

Discovery: DexScreener token-boosts/latest + token-boosts/top (recently
boosted = freshly launched tokens), then batch pair lookup per token.
DBC pairs = dexId "meteora" or labels DLMM/DYN2/DBC.

Usage: python3 fresh_battery.py [count=5]
Requires: dbc_state.js microservice (port 8077) for on-chain DBC state.
"""
import json, time, urllib.request, sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

UA = {"User-Agent": "Mozilla/5.0"}

DBC_LABELS = ("DLMM", "DYN2", "DBC")


def get_json(url):
    req = urllib.request.Request(url, headers=UA)
    return json.load(urllib.request.urlopen(req, timeout=25))


def collect_candidate_mints():
    """Recently boosted Solana tokens = freshest launches on the market."""
    mints, seen = [], set()
    for url in (
        "https://api.dexscreener.com/token-boosts/latest/v1",
        "https://api.dexscreener.com/token-boosts/top/v1",
    ):
        try:
            arr = get_json(url)
        except Exception:
            continue
        for t in arr:
            a = t.get("tokenAddress")
            if t.get("chainId") == "solana" and a and a not in seen:
                seen.add(a)
                mints.append(a)
    return mints


def lookup_pairs(mints):
    """Batch pair lookup, up to 30 addresses per request."""
    pairs = []
    for i in range(0, len(mints), 28):
        batch = ",".join(mints[i:i + 28])
        try:
            d = get_json(f"https://api.dexscreener.com/latest/dex/tokens/{batch}")
            pairs.extend(d.get("pairs") or [])
        except Exception:
            continue
    return pairs


def is_dbc_pair(p):
    if p.get("dexId") == "meteora":
        return True
    labels = str(p.get("labels") or "")
    return any(x in labels for x in DBC_LABELS)


def classify_pairs(pairs):
    """Best pair per mint (meteora preferred), split into DBC / other, fresh / recent."""
    now = time.time() * 1000
    best = {}
    for p in pairs:
        if p.get("chainId") != "solana":
            continue
        mint = (p.get("baseToken") or {}).get("address", "")
        if not mint:
            continue
        rank = (1 if is_dbc_pair(p) else 0,
                (p.get("liquidity") or {}).get("usd") or 0)
        if mint not in best or rank > best[mint][0]:
            best[mint] = (rank, p)

    fresh_dbc, fresh_other, recent_dbc = [], [], []
    for mint, (_, p) in best.items():
        b = p.get("baseToken") or {}
        liq = (p.get("liquidity") or {}).get("usd") or 0
        v24 = (p.get("volume") or {}).get("h24") or 0
        age_h = (now - (p.get("pairCreatedAt") or 0)) / 3600000
        row = {
            "mint": mint,
            "symbol": b.get("symbol", "?"),
            "pair": p.get("pairAddress", ""),
            "age_h": round(age_h, 1),
            "mcap_k": round((p.get("marketCap") or 0) / 1e3),
            "liq_k": round(liq / 1e3, 1),
            "vol24_k": round(v24 / 1e3),
            "dex": p.get("dexId", "?"),
        }
        dbc = is_dbc_pair(p)
        if age_h <= 72 and liq >= 5_000 and v24 >= 10_000:
            (fresh_dbc if dbc else fresh_other).append(row)
        elif dbc and age_h <= 168 and liq >= 5_000:
            recent_dbc.append(row)

    for lst in (fresh_dbc, fresh_other, recent_dbc):
        lst.sort(key=lambda x: -x["vol24_k"])
    return fresh_dbc, fresh_other, recent_dbc


def print_table(rows, title):
    print(f"\n--- {title} ---")
    if not rows:
        print("  (none)")
        return
    print(f"  {'Token':14} {'Age':>7} {'Liq':>9} {'Vol24':>10} {'MCap':>9}  DEX")
    for r in rows:
        print(f"  {r['symbol']:14} {str(r['age_h']) + 'h':>7} "
              f"${r['liq_k']:>7,.0f}K ${r['vol24_k']:>8,.0f}K ${r['mcap_k']:>7,}K  {r['dex']}")


def scan(mint, symbol, tag=""):
    print(f"\n🔍 {symbol} ({mint[:12]}...) {tag}")
    try:
        from dbc_scanner import score_launch
        r = score_launch(mint)
        if "error" in r:
            print(f"  ERROR: {r['error'][:100]}")
            return None
        print(f"  Score: {r.get('score', 0)}/100 | Tier: {r.get('tier', '?')}")
        for name, c in (r.get("components") or {}).items():
            notes = c.get("notes", c.get("note", ""))
            if notes:
                print(f"    {name}: {c.get('score', '?')} | {notes}")
        return {"symbol": symbol, "mint": mint,
                "score": r.get("score", 0), "tier": r.get("tier", "?")}
    except Exception as e:
        print(f"  scan error: {e}")
        return None


def run_battery(count=5):
    print("=== FRESH DBC LAUNCH BATTERY ===\n")

    mints = collect_candidate_mints()
    if not mints:
        print("discovery failed: boosts endpoints unreachable?")
        return
    pairs = lookup_pairs(mints)
    fresh_dbc, fresh_other, recent_dbc = classify_pairs(pairs)
    print(f"checked {len(mints)} fresh candidates "
          f"({len(fresh_dbc)} fresh DBC, {len(fresh_other)} fresh other, "
          f"{len(recent_dbc)} recent DBC)")

    print_table(fresh_dbc + fresh_other[:10], f"fresh launches (<72h, all DEXes)")
    print_table(recent_dbc, "recent DBC launches (72h-7d, scan fallback)")

    targets = fresh_dbc[:count] or recent_dbc[:count]
    if not targets:
        print("\nno scannable DBC launch right now.")
        print("fresh launches above are on other DEXes (pumpswap/raydium etc).")
        print("DBC launches drop intermittently - re-run during the 7-9 PM VN window,")
        print("or scan any CA directly:  python3 dbc_scanner.py <MINT>")
        return

    label = "fresh" if fresh_dbc else "recent (older) DBC"
    print(f"\n--- RUNNING SAFETY SCANNER on {len(targets)} {label} launch(es) ---")
    results = []
    for f in targets:
        r = scan(f["mint"], f["symbol"], tag=f"[{f['age_h']}h, liq ${f['liq_k']:.0f}K]")
        if r:
            results.append(r)
        time.sleep(1)

    print("\n=== BATTERY RESULTS ===\n")
    print(f"{'Token':16} {'Score':6} {'Tier'}")
    print("-" * 40)
    for r in sorted(results, key=lambda x: -x.get("score", 0)):
        print(f"  {r['symbol']:14} {r['score']:3}/100 {r['tier']}")
    print()
    best = max(results, key=lambda x: x.get("score", 0)) if results else None
    if best:
        print(f"🏆 Best candidate: {best['symbol']} ({best['score']}/100 {best['tier']})")


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    run_battery(count)
