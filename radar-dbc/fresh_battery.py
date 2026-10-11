#!/usr/bin/env python3
"""
fresh_battery.py - Fresh DBC launch battery
Finds new Meteora DBC launches and runs the safety scanner on each.
Usage: python3 fresh_battery.py [count=5]

Finds launches from DexScreener (Meteora DLMM pairs, <24h old, real volume)
and runs dbc_scanner.py logic on each. Outputs a ranked table.
"""
import json, time, urllib.request, sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

UA = {"User-Agent": "Mozilla/5.0"}

def get_json(url):
    req = urllib.request.Request(url, headers=UA)
    return json.load(urllib.request.urlopen(req, timeout=25))

def find_fresh_dbc(count=5):
    """Find fresh Meteora DLMM/DBC pairs < 24h old with real volume."""
    dd = get_json("https://api.dexscreener.com/latest/dex/search?q=solana")
    ps = dd.get("pairs") or []
    now = time.time() * 1000
    fresh = []
    seen_mints = set()
    for p in ps:
        if p.get("chainId") != "solana": continue
        liq = (p.get("liquidity") or {}).get("usd") or 0
        v24 = (p.get("volume") or {}).get("h24") or 0
        created = p.get("pairCreatedAt") or 0
        age_h = (now - created) / 3600000
        if liq < 10_000 or v24 < 50_000 or age_h > 48: continue
        b = (p.get("baseToken") or {})
        mint = b.get("address", "")
        if mint in seen_mints: continue
        seen_mints.add(mint)
        fresh.append({
            "mint": mint,
            "symbol": b.get("symbol", "?"),
            "pair": p.get("pairAddress", ""),
            "age_h": round(age_h, 1),
            "mcap_k": round((p.get("marketCap") or 0) / 1e3),
            "liq_k": round(liq / 1e3, 1),
            "vol24_m": round(v24 / 1e6, 2),
            "dex": p.get("dexId", "?"),
        })
        if len(fresh) >= count * 2: break  # collect extra in case some fail
    fresh.sort(key=lambda x: -x["vol24_m"])
    return fresh[:count]

def run_battery(count=5):
    print("=== FRESH DBC LAUNCH BATTERY ===\n")
    fresh = find_fresh_dbc(count)
    if not fresh:
        print("no fresh DBC launches found right now")
        return
    print(f"found {len(fresh)} fresh launches:\n")
    for f in fresh:
        print(f"  {f['symbol']} | {f['age_h']}h old | mcap ${f['mcap_k']}K | liq ${f['liq_k']}K | vol ${f['vol24_m']}M")
    print("\n--- RUNNING SAFETY SCANNER ---\n")
    results = []
    for f in fresh:
        mint = f["mint"]
        symbol = f["symbol"]
        print(f"\n🔍 {symbol} ({mint[:12]}...)")
        try:
            # import scanner logic inline
            from dbc_scanner import score_launch
            r = score_launch(mint)
            if "error" in r:
                print(f"  ERROR: {r['error'][:80]}")
                continue
            tier = r.get("tier", "?")
            score = r.get("score", 0)
            comps = r.get("components", {})
            print(f"  Score: {score}/100 | Tier: {tier}")
            for name, c in comps.items():
                notes = c.get("notes", c.get("note", ""))
                if notes: print(f"    {name}: {c.get('score', '?')} | {notes}")
            results.append({"symbol": symbol, "mint": mint, "score": score, "tier": tier})
        except Exception as e:
            print(f"  scan error: {e}")
        time.sleep(1)

    # summary table
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
