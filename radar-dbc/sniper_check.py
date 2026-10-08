#!/usr/bin/env python3
"""
sniper_check.py - Day 2: sniper overlap component for radar-dbc
Detects first-block buyers of a DBC pool and checks if they still hold.

Usage (called from dbc_scanner.py):
    from sniper_check import sniper_overlap
    result = sniper_overlap(pool_address, max_sigs=50)
"""
import json, time, urllib.request
from collections import defaultdict

UA = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
RPCS = ["https://api.mainnet-beta.solana.com", "https://api.mainnet-beta.solana.com",
        "https://solana-rpc.publicnode.com"]
_idx = [0]

def rpc(method, params, timeout=25):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    last = None
    for attempt in range(len(RPCS) * 2):
        url = RPCS[_idx[0] % len(RPCS)]
        try:
            req = urllib.request.Request(url, data=body, headers=UA)
            r = json.load(urllib.request.urlopen(req, timeout=timeout))
            if "error" in r:
                err = r["error"]
                if err.get("code") in (429, 413):
                    _idx[0] += 1; time.sleep(1.5); continue
                return None
            return r.get("result")
        except Exception as e:
            last = e; _idx[0] += 1; time.sleep(1.2)
    return None

def earliest_buyers(pool_address, max_sigs=40, sample_sigs=12):
    """
    Walk a pool's tx history back to its earliest transactions.
    Returns dict: buyer_wallet -> first_seen_ts (from earliest sample).
    We page backwards (before=) up to max_sigs total, sampling the OLDEST ones.
    """
    before = None
    oldest_batch = []
    pages = 0
    while pages < 6:  # bounded paging (each page ~1000 sigs on active pools)
        params = [pool_address, {"limit": 1000}]
        if before: params[1]["before"] = before
        res = rpc("getSignaturesForAddress", params)
        if not res or len(res) == 0: break
        oldest_batch = res
        if len(res) < 1000:  # reached the beginning
            break
        before = res[-1]["signature"]
        pages += 1
        time.sleep(0.4)
    if not oldest_batch:
        return {}
    # oldest N signatures
    oldest = oldest_batch[-sample_sigs:]
    buyers = {}
    for s in oldest:
        if s.get("err"): continue
        sig = s["signature"]
        tx = rpc("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])
        time.sleep(0.3)
        if not tx: continue
        keys = [k["pubkey"] if isinstance(k, dict) else k
                for k in tx["transaction"]["message"]["accountKeys"]]
        # buyers = accounts that SOL-decreased in the earliest txs (bought base token)
        pre = tx.get("meta", {}).get("preBalances") or []
        post = tx.get("meta", {}).get("postBalances") or []
        for i, (a, b) in enumerate(zip(pre, post)):
            if i >= len(keys): break
            if (b - a) / 1e9 > 0.01 and keys[i] != keys[0]:  # spent >0.01 SOL, not fee payer skip
                buyers[keys[i]] = s.get("blockTime") or 0
        # cap: first buyers found
        if len(buyers) >= 10: break
    return buyers

def still_holding(buyer, base_mint, contract="TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"):
    """Check if buyer still holds any of the base token (largest token accounts)."""
    # getTokenAccountsByOwner is indexed on most RPCs; mainnet-beta allows it
    res = rpc("getTokenAccountsByOwner",
              [buyer, {"mint": base_mint}, {"encoding": "jsonParsed"}])
    if not res: return None  # unknown (RPC blocked) - neutral
    accs = res.get("result", {}).get("value", [])
    for a in accs:
        info = (a.get("account", {}).get("data", {}) or {}).get("parsed", {}).get("info", {})
        if int(info.get("tokenAmount", {}).get("amount", "0")) > 0:
            return True
    return False

def sniper_overlap(pool_address, base_mint, max_sigs=40):
    buyers = earliest_buyers(pool_address, max_sigs=max_sigs)
    if not buyers:
        return {"checked": 0, "still_holding": 0, "ratio": None,
                "note": "no early buyer data (RPC limits)"}
    holding, unknown = 0, 0
    details = []
    for w, ts in list(buyers.items())[:10]:
        h = still_holding(w, base_mint)
        if h is None: unknown += 1; continue
        if h: holding += 1
        details.append({"wallet": w[:8] + "..", "still_holding": h})
        time.sleep(0.3)
    checked = len(details)
    ratio = (holding / checked) if checked else None
    return {"checked": checked, "still_holding": holding,
            "ratio": round(ratio, 2) if ratio is not None else None,
            "unknown": unknown, "details": details[:5]}

if __name__ == "__main__":
    import sys
    pool, mint = sys.argv[1], sys.argv[2]
    print(json.dumps(sniper_overlap(pool, mint), indent=1))
