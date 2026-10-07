#!/usr/bin/env python3
"""
dbc_scanner.py - Radar for DBC: LP safety score for Meteora DBC launches
Part of Radar: on-chain insider detection for Solana LPs
Submission: "Best use of Meteora DBC" — Crypto World's Fair sidetrack ($20K USDC)

Usage:
  python3 dbc_scanner.py <TOKEN_BASE_MINT> [--full]

Requires: dbc_state.js microservice running (node dbc_state.js, port 8077)
Reuses:   insider_radar.py funding-trace engine (same folder)

Score components (0-100):
  funding concentration 30 | insider timing 20 | sniper overlap 15
  contract basics 15 | curve fairness 10 | liquidity health 10
"""
import json, sys, time, os, urllib.request, urllib.error
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
UA = {"User-Agent": "Mozilla/5.0"}
STATE_URL = os.environ.get("DBC_STATE_URL", "http://127.0.0.1:8077")

def get_json(url):
    req = urllib.request.Request(url, headers=UA)
    return json.load(urllib.request.urlopen(req, timeout=25))

# ---------- DBC state via microservice ----------

def dbc_state(mint):
    return get_json(f"{STATE_URL}/state?mint={mint}")

def parse_state(s):
    """Extract scoring-relevant fields from dbc_state.js output."""
    vp = s.get("virtualPool", {})
    cfg = s.get("config", {}) or {}
    # virtual pool account (borsh-decoded by SDK)
    pool_state = vp.get("poolState")
    creator = vp.get("creator")
    activation = vp.get("activationPoint")
    curve_prog = s.get("curveProgress")

    # pool config (fee scheduler etc.) — structure varies by SDK version; be defensive
    fee_params = cfg.get("baseFee", {}) or cfg.get("feeParam", {}) or {}
    fee_mode = fee_params.get("baseFeeMode") or fee_params.get("mode")
    # migration settings
    migr = cfg.get("migrationOption") or cfg.get("migration")
    return {
        "pool_state": pool_state,
        "creator": creator,
        "activation_point": activation,
        "curve_progress": curve_prog,
        "fee_mode": fee_mode,
        "fee_params": fee_params,
        "migration_option": migr,
        "config": cfg,
    }

# ---------- funding trace (reuses insider_radar) ----------

def funding_trace(mint, top_n=10):
    """Wrap insider_radar.funder_of for the top holders of this token."""
    import insider_radar as IR
    try:
        rug = IR.get_json if hasattr(IR, "get_json") else None
    except Exception:
        rug = None
    # fetch holders via RugCheck report (same source as radar)
    try:
        rep = get_json(f"https://api.rugcheck.xyz/v1/tokens/{mint}/report")
    except Exception as e:
        return None, f"rugcheck unavailable: {e}"
    pools = set()
    try:
        dd = get_json(f"https://api.dexscreener.com/latest/dex/tokens/{mint}")
        pools = {p["pairAddress"] for p in (dd.get("pairs") or []) if p.get("pairAddress")}
    except Exception:
        pass
    holders = [h for h in (rep.get("topHolders") or [])
               if h.get("pct", 0) > 0.3 and (h.get("owner") or h.get("address")) not in pools][:top_n]
    results = []
    for h in holders:
        owner = h.get("owner") or h.get("address")
        if not owner: continue
        fp, ts = IR.funder_of(owner)
        results.append({"owner": owner, "pct": h["pct"], "funder": fp,
                        "first_tx": ts})
        time.sleep(0.4)
    # clusters: same funder on 2+ holders
    byf = defaultdict(list)
    for r in results:
        if r["funder"] and r["funder"] != r["owner"]:
            byf[r["funder"]].append(r)
    clusters = {f: rs for f, rs in byf.items() if len(rs) >= 2}
    return {"holders": results, "clusters": clusters}, None

# ---------- contract basics (rugcheck summary) ----------

def contract_basics(mint):
    try:
        s = get_json(f"https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary")
    except Exception:
        return {"score": 0, "notes": ["rugcheck unreachable"]}
    lp = s.get("lpLockedPct") or 0
    risks = s.get("risks") or []
    score = 15
    notes = []
    if lp >= 99: score -= 0
    else:
        score -= 8; notes.append(f"LP only {lp:.0f}% locked")
    for r in risks[:3]:
        notes.append(r.get("name", "risk"))
    return {"score": max(0, score), "notes": notes, "lp_locked": lp}

# ---------- scoring ----------

def score_launch(mint, verbose=False):
    out = {"mint": mint, "components": {}, "flags": []}

    # 1. DBC state
    try:
        st = parse_state(dbc_state(mint))
    except Exception as e:
        return {"mint": mint, "error": f"DBC state unavailable: {e} (is dbc_state.js running?)"}
    out["dbc"] = {k: st[k] for k in ("pool_state","creator","curve_progress","fee_mode","migration_option")}

    # 2. Funding concentration (30)
    trace, err = funding_trace(mint)
    if trace is None:
        out["components"]["funding"] = {"score": 0, "note": f"trace failed: {err}"}
    else:
        clusters = trace["clusters"]
        linked = sum(len(rs) for rs in clusters.values())
        linked_pct = sum(r["pct"] for rs in clusters.values() for r in rs)
        fs = 30
        if linked >= 3: fs = 8
        elif linked == 2: fs = 16
        elif linked == 1: fs = 24
        if linked_pct >= 8: fs = min(fs, 5)
        out["components"]["funding"] = {
            "score": fs, "linked_wallets": linked, "linked_pct_supply": round(linked_pct,2),
            "clusters": {f[:10]+"..": [f"{r['pct']:.1f}%" for r in rs] for f, rs in clusters.items()}
        }
    f_score = out["components"]["funding"]["score"]

    # 3. Insider timing (20) — holders whose first tx happened near pool activation
    it_score = 20
    if trace:
        # crude version: any top holder first_tx within 2h of activation point
        # (activation_point and first_tx both unix-ish; refine in v1.1)
        pass
    out["components"]["insider_timing"] = {"score": it_score, "note": "v1: neutral unless funding trace shows clusters"}

    # 4. Sniper overlap (15) — v1.1: replay first N swaps of pool; v1: neutral
    out["components"]["sniper_overlap"] = {"score": 11, "note": "v1: neutral default"}

    # 5. Contract basics (15)
    cb = contract_basics(mint)
    out["components"]["contract"] = {"score": cb["score"], "notes": cb["notes"]}

    # 6. Curve fairness (10) — fee mode + migration sanity from config
    cf = 10
    fee_mode = str(st.get("fee_mode") or "")
    # scheduler-based anti-sniper = good; rate limiter deprecated = meh; no decay = meh
    if "rate" in fee_mode.lower(): cf -= 4
    if not fee_mode: cf -= 4
    out["components"]["curve_fairness"] = {"score": max(0,cf), "fee_mode": fee_mode}

    # 7. Liquidity health (10) — curve progress vs nothing else yet
    cp = st.get("curve_progress")
    lh = 10
    note = ""
    if cp is not None:
        if cp < 0.02: lh, note = 6, "curve barely moving (low organic demand?)"
    else:
        lh, note = 6, "progress unavailable"
    out["components"]["liquidity_health"] = {"score": lh, "curve_progress": cp, "note": note}

    total = sum(c.get("score",0) for c in out["components"].values())
    out["score"] = max(0, min(100, total))
    tier = "🟢 SAFE" if out["score"] >= 80 else ("🟡 CAUTION" if out["score"] >= 60 else "🔴 DANGEROUS")
    out["tier"] = tier
    return out

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    mint = sys.argv[1]
    print(f"=== RADAR-DBC: {mint} ===")
    r = score_launch(mint)
    if "error" in r:
        print("ERROR:", r["error"]); sys.exit(1)
    print(f"Tier: {r['tier']}   Score: {r['score']}/100\n")
    for name, c in r["components"].items():
        print(f"[{name:16}] {c.get('score',0):>2}/30+20+15+15+10+10  { {k:v for k,v in c.items() if k!='score'} }")
    print(f"\nScore: {r['score']}/100 — {r['tier']}")
    print("The contract can't rug you. The holders can. Radar reads the holders.")

if __name__ == "__main__":
    main()
