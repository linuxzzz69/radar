#!/usr/bin/env python3
"""
fresh_battery.py - Fresh DBC launch battery
Finds brand-new Solana pool launches via GeckoTerminal new_pools feed,
isolates Meteora DBC launches (dex id "meteora-dbc"), enriches each with
DexScreener market data, and runs the safety scanner on every DBC candidate.

Usage: python3 fresh_battery.py [count=5] [pages=4]
Requires: dbc_state.js microservice (port 8077) for on-chain DBC state.
"""
import json, time, urllib.request, sys, os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def get_json(url):
    req = urllib.request.Request(url, headers=UA)
    return json.load(urllib.request.urlopen(req, timeout=25))


def iso_age_h(iso):
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - t).total_seconds() / 3600
    except Exception:
        return None


def collect_new_pools(pages=4):
    """Newest pools on Solana from GeckoTerminal (20 per page)."""
    pools = []
    for pg in range(1, pages + 1):
        try:
            d = get_json(f"https://api.geckoterminal.com/api/v2/networks/solana/new_pools?page={pg}")
            pools.extend(d.get("data") or [])
        except Exception:
            break
        time.sleep(1.2)  # free tier: 30 calls/min
    return pools


def extract_rows(pools):
    """Split into DBC launches and other fresh launches; dedup by base mint."""
    dbc, other = [], []
    seen = set()
    for p in pools:
        rel = p.get("relationships") or {}
        dex = (rel.get("dex") or {}).get("data", {}).get("id", "")
        mint = (((rel.get("base_token") or {}).get("data") or {}).get("id") or "").replace("solana_", "")
        quote = (((rel.get("quote_token") or {}).get("data") or {}).get("id") or "").replace("solana_", "")
        a = p.get("attributes") or {}
        if not mint or mint in seen:
            continue
        age_h = iso_age_h(a.get("pool_created_at") or "")
        if age_h is None or age_h > 72:
            continue
        fdv = float(a.get("fdv_usd") or 0)
        vol = float(((a.get("volume_usd") or {}).get("h24")) or 0)
        row = {
            "mint": mint,
            "symbol": (a.get("name") or "?").split(" / ")[0],
            "pool": a.get("address", ""),
            "quote": quote,
            "age_h": round(age_h, 1),
            "fdv_k": round(fdv / 1e3),
            "vol24_k": round(vol / 1e3),
            "dex": dex,
        }
        seen.add(mint)
        if dex == "meteora-dbc":
            # dust filter: clone/dust DBC pools launch constantly
            if fdv >= 5_000:
                dbc.append(row)
        elif fdv >= 50_000:
            other.append(row)
    for lst in (dbc, other):
        lst.sort(key=lambda x: -x["vol24_k"])
    return dbc, other


def enrich(rows):
    """Add DexScreener liquidity/mcap/labels where available."""
    mints = [r["mint"] for r in rows]
    for i in range(0, len(mints), 28):
        try:
            d = get_json(f"https://api.dexscreener.com/latest/dex/tokens/{','.join(mints[i:i+28])}")
        except Exception:
            continue
        bymint = {}
        for p in d.get("pairs") or []:
            m = (p.get("baseToken") or {}).get("address", "")
            better = (p.get("liquidity") or {}).get("usd") or 0 > bymint.get(m, (0, {}))[0]
            if better:
                bymint[m] = ((p.get("liquidity") or {}).get("usd") or 0, p)
        for r in rows[i:i+28]:
            liq, p = bymint.get(r["mint"], (None, None))
            if p:
                r["liq_k"] = round((liq or 0) / 1e3)
                r["mcap_k"] = round((p.get("marketCap") or 0) / 1e3)
                r["labels"] = p.get("labels") or []
        time.sleep(0.5)
    return rows


def print_table(rows, title):
    print(f"\n--- {title} ---")
    if not rows:
        print("  (none)")
        return
    print(f"  {'Token':14} {'Age':>7} {'FDV':>9} {'Vol24':>9}  DEX")
    for r in rows:
        print(f"  {r['symbol']:14} {str(r['age_h']) + 'h':>7} "
              f"${r['fdv_k']:>7,}K ${r['vol24_k']:>7,}K  {r['dex']}")


def scan(mint, symbol, tag=""):
    print(f"\n🔍 {symbol} ({mint[:12]}...) {tag}")
    try:
        from dbc_scanner import score_launch
        r = score_launch(mint)
        if "error" in r:
            print(f"  ERROR: {r['error'][:110]}")
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


def run_battery(count=5, pages=4):
    print("=== FRESH DBC LAUNCH BATTERY ===\n")

    pools = collect_new_pools(pages)
    dbc, other = extract_rows(pools)
    print(f"checked {len(pools)} newest Solana pools "
          f"({len(dbc)} DBC launches, {len(other)} fresh other-DEX launches)")

    if dbc:
        dbc = enrich(dbc)
    print_table(dbc, "fresh Meteora DBC launches (<72h)")
    print_table(other[:10], "fresh launches, other DEXes (<72h)")

    if not dbc:
        print("\nno DBC launch in the newest pools right now.")
        print("DBC launches drop every few hours - re-run in 1-2 hours,")
        print("or scan any CA directly:  python3 dbc_scanner.py <MINT>")
        return

    targets = dbc[:count]
    print(f"\n--- RUNNING SAFETY SCANNER on {len(targets)} DBC launch(es) ---")
    results = []
    for f in targets:
        liq_s = f"liq ${f.get('liq_k', f['fdv_k']):.0f}K" if f.get("liq_k") else f"fdv ${f['fdv_k']:.0f}K"
        r = scan(f["mint"], f["symbol"], tag=f"[{f['age_h']}h, {liq_s}]")
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
    pages = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    run_battery(count, pages)
