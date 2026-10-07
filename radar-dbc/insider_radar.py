#!/usr/bin/env python3
"""
insider_radar.py - Solana memecoin insider radar
Usage: python3 insider_radar.py <TOKEN_CA> [top_n=15] [trace_depth=2]

1. Pulls top holders from RugCheck
2. Traces each holder wallet's FIRST transaction via Solana RPC
3. Extracts the funding ancestor (fee payer / funder of first tx)
4. Clusters holders sharing funding ancestors -> insider web
"""
import json, sys, time, urllib.request, urllib.error
from collections import defaultdict

PUBLICNODE = "https://solana-rpc.publicnode.com"
MAINNET = "https://api.mainnet-beta.solana.com"
UA = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}

def rpc(url, method, params, retries=3):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for i in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers=UA)
            r = json.load(urllib.request.urlopen(req, timeout=20))
            if "error" in r:
                err = r["error"]
                if err.get("code") == 429:
                    time.sleep(2 + i * 2); continue
                return None
            return r.get("result")
        except Exception:
            time.sleep(1 + i)
    return None

def get(url):
    req = urllib.request.Request(url, headers=UA)
    return json.load(urllib.request.urlopen(req, timeout=25))

def first_signatures(wallet, max_pages=3):
    """Walk back to the wallet's oldest transaction."""
    sigs, before = [], None
    for _ in range(max_pages):
        params = [wallet, {"limit": 1000}]
        if before: params[1]["before"] = before
        res = rpc(PUBLICNODE, "getSignaturesForAddress", params)
        if not res: break
        if len(res) < 1000:
            sigs = res + sigs if not sigs else res + sigs
            if not res: break
            return res  # reached genesis: res is oldest page
        before = res[-1]["signature"]
        sigs = res + sigs if not sigs else sigs
        time.sleep(0.4)
    return sigs if not before else (res if res else sigs[:3])

def first_3_sigs(wallet):
    """Cheaper: just try fetching the oldest page directly."""
    res = rpc(PUBLICNODE, "getSignaturesForAddress", [wallet, {"limit": 1000}])
    if not res:
        time.sleep(0.8)
        res = rpc(MAINNET, "getSignaturesForAddress", [wallet, {"limit": 1000}])
    if not res: return []
    if len(res) < 1000:
        return res[-3:] if len(res) >= 3 else res
    # page back up to 3 times
    before = res[-1]["signature"]
    for _ in range(3):
        time.sleep(0.4)
        res2 = rpc(PUBLICNODE, "getSignaturesForAddress", [wallet, {"limit": 1000, "before": before}])
        if not res2:
            time.sleep(0.8)
            res2 = rpc(MAINNET, "getSignaturesForAddress", [wallet, {"limit": 1000, "before": before}])
        if not res2: return res[-3:]
        if len(res2) < 1000:
            return res2[-3:]
        before = res2[-1]["signature"]
        res = res2
    return res2[-3:] if res2 else []

def fetch_tx(url, sig):
    for ver in (0, 1):
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getTransaction",
                           "params": [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": ver}]}).encode()
        try:
            req = urllib.request.Request(url, data=body, headers=UA)
            r = json.load(urllib.request.urlopen(req, timeout=25))
            if "error" in r:
                msg = r["error"].get("message", "")
                if ver == 0 and "not supported" in msg:
                    continue  # retry with v1
                return None
            return r.get("result")
        except Exception:
            return None
    return None

def funder_of(wallet):
    """Return the fee payer / SOL source of the wallet's first tx."""
    sigs = first_3_sigs(wallet)
    if not sigs: return None, None
    sig = sigs[0]["signature"]
    tx = fetch_tx(PUBLICNODE, sig)
    time.sleep(0.4)
    if not tx:
        tx = fetch_tx(MAINNET, sig)
        time.sleep(0.5)
    if not tx: return None, None
    try:
        msg = tx["transaction"]["message"]
        keys = msg["accountKeys"]
        fee_payer = keys[0]["pubkey"] if isinstance(keys[0], dict) else keys[0]
        ts = tx.get("blockTime")
        return fee_payer, ts
    except Exception:
        return None, None

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    ca = sys.argv[1]
    top_n = int(sys.argv[2]) if len(sys.argv) > 2 else 15

    print(f"=== INSIDER RADAR: {ca} ===")
    rep = get(f"https://api.rugcheck.xyz/v1/tokens/{ca}/report")
    meta = rep.get("tokenMeta") or {}
    symbol = (meta.get("symbol") or "?")
    print(f"Token: {symbol} | holders: {rep.get('totalHolders')} | rugged: {rep.get('rugged')}")

    # exclude DEX pool accounts from tracing
    pools = set()
    try:
        dd = get(f"https://api.dexscreener.com/latest/dex/tokens/{ca}")
        for p in (dd.get("pairs") or []):
            if p.get("pairAddress"): pools.add(p["pairAddress"])
    except Exception:
        pass

    holders = [h for h in (rep.get("topHolders") or []) if h.get("pct", 0) > 0.3][:top_n]
    traced = [h for h in holders if (h.get("owner") or h.get("address")) not in pools]
    skipped = len(holders) - len(traced)
    if skipped: print(f"(skipped {skipped} DEX pool accounts)")
    holders = traced[:top_n]
    print(f"Tracing top {len(holders)} holders (wallet -> funding ancestor)...\n")

    results = []
    for i, h in enumerate(holders, 1):
        owner = h.get("owner") or h.get("address")
        if not owner: continue
        fp, ts = funder_of(owner)
        results.append({"rank": i, "owner": owner, "pct": h["pct"], "funder": fp, "first_tx": ts})
        tag = " [RUGCHECK-INSIDER]" if h.get("insider") else ""
        print(f"  #{i:<2} {h['pct']:5.1f}%  {owner[:8]}..{owner[-4:]}  <- funder {str(fp)[:8]}..{str(fp)[-4:] if fp else '?'}{tag}")
        time.sleep(0.5)

    # cluster funders
    by_funder = defaultdict(list)
    for r in results:
        if r["funder"] and r["funder"] != r["owner"]:
            by_funder[r["funder"]].append(r)

    print("\n=== FUNDING CLUSTERS (same wallet funded multiple top holders) ===")
    clusters = {f: rs for f, rs in by_funder.items() if len(rs) >= 2}
    if not clusters:
        print("  None found - top holders were funded independently.")
    else:
        for f, rs in sorted(clusters.items(), key=lambda kv: -len(kv[1])):
            total_pct = sum(r["pct"] for r in rs)
            print(f"  FUNDER {f}")
            for r in rs:
                print(f"     -> holder {r['owner'][:8]}..  {r['pct']:.1f}%")
            print(f"     == cluster controls {total_pct:.1f}% of supply via {len(rs)} linked wallets")

    flagged = sum(len(rs) for rs in clusters.values())
    print(f"\nVERDICT: {flagged}/{len(results)} top holders linked by funding."
          + ("  INSIDER WEB DETECTED - treat as insider coin." if flagged >= 3 else "  No strong insider web from funding ancestry."))

if __name__ == "__main__":
    main()
