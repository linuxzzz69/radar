#!/usr/bin/env python3
"""smart_hunter.py - find wallets with REALIZED profit on a token.
Bought early + sold into strength = proven smart money. No holders-only guesswork.
"""
import json, time, urllib.request
from collections import defaultdict

UA={"User-Agent":"Mozilla/5.0","Content-Type":"application/json"}

def rpc(m,p):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode()
    for url in ["https://api.mainnet-beta.solana.com","https://solana-rpc.publicnode.com"]:
        try:
            r=json.load(urllib.request.urlopen(urllib.request.Request(url,data=body,headers=UA),timeout=25))
            if "error" in r:
                time.sleep(1); continue
            return r.get("result")
        except Exception:
            time.sleep(1)
    return None

def dexscreener(mint):
    try:
        r=json.load(urllib.request.urlopen(urllib.request.Request(
            f"https://api.dexscreener.com/latest/dex/tokens/{mint}",headers={"User-Agent":"Mozilla/5.0"}),timeout=15))
        return r.get("pairs") or []
    except Exception:
        return []

def hunt(mint, pool_address=None, sample=40):
    """Return list of wallets with realized PnL on this token (recent window)."""
    ps = dexscreener(mint)
    if not pool_address:
        real = [p for p in ps if (p.get('liquidity') or {}).get('usd',0) > 10_000]
        if not real: return [], None
        pool_address = sorted(real, key=lambda p:-((p.get('liquidity') or {}).get('usd') or 0))[0].get('pairAddress')
    sigs=[]
    before=None
    for i in range(2):
        params=[pool_address,{"limit":1000}]
        if before: params[1]["before"]=before
        res=rpc("getSignaturesForAddress",params) or []
        if not res: break
        sigs+=res
        if len(res)<1000: break
        before=res[-1]["signature"]
        time.sleep(0.5)
    sigs=[s for s in sigs if not s.get('err')]
    ledger={}
    scanned=0
    for s in sigs[:sample]:
        tx=rpc("getTransaction",[s["signature"],{"encoding":"jsonParsed","maxSupportedTransactionVersion":0}])
        time.sleep(0.25)
        scanned+=1
        if not tx: continue
        meta=tx.get("meta") or {}
        if meta.get("err"): continue
        keys=[k["pubkey"] if isinstance(k,dict) else k for k in tx["transaction"]["message"]["accountKeys"]]
        pre_bal=meta.get("preBalances") or []
        post_bal=meta.get("postBalances") or []
        ptb=meta.get("preTokenBalances") or []
        ptb2=meta.get("postTokenBalances") or []
        # per-mint token maps
        pre={}
        for b in ptb:
            o=b.get("owner")
            if o: pre.setdefault(o,{})[b.get("mint","")]=int(b["uiTokenAmount"]["amount"])
        post={}
        for b in ptb2:
            o=b.get("owner")
            if o: post.setdefault(o,{})[b.get("mint","")]=int(b["uiTokenAmount"]["amount"])
        ts=s.get("blockTime") or 0
        users=set(list(pre.keys())+list(post.keys()))
        for w in users:
            if w not in keys or w==keys[0]: continue
            i=keys.index(w)
            if i>=len(pre_bal): continue
            d_sol=(post_bal[i]-pre_bal[i])/1e9
            # find the token mint with a delta for this wallet
            for m in set(list(pre.get(w,{}).keys())+list(post.get(w,{}).keys())):
                if m.startswith("So11111111"): continue  # skip SOL itself
                d_tok=post.get(w,{}).get(m,0)-pre.get(w,{}).get(m,0)
                if d_tok>0 and d_sol<-0.0005:
                    e=ledger.setdefault(w,{"bought_sol":0,"sold_sol":0,"buys":0,"sells":0,"mints":set()})
                    e["bought_sol"]+=abs(d_sol); e["buys"]+=1; e["mints"].add(m[:6])
                elif d_tok<0 and d_sol>0.0005:
                    e=ledger.setdefault(w,{"bought_sol":0,"sold_sol":0,"buys":0,"sells":0,"mints":set()})
                    e["sold_sol"]+=d_sol; e["sells"]+=1; e["mints"].add(m[:6])
    winners=[]
    for w,e in ledger.items():
        if e["sells"]>0 and e["sold_sol"]>e["bought_sol"]*1.1:
            winners.append({"wallet":w,"net_sol":round(e["sold_sol"]-e["bought_sol"],3),
                            "bought":e["bought_sol"],"sold":e["sold_sol"],"buys":e["buys"],"sells":e["sells"]})
    winners.sort(key=lambda x:-x["net_sol"])
    return winners[:8], pool_address

if __name__=="__main__":
    import sys
    mint=sys.argv[1]
    w,p=hunt(mint)
    print(f"pool: {p}")
    for x in (w or [])[:8]:
        print(f"{x['wallet']} | net +{x['net_sol']} SOL | {x['buys']}B/{x['sells']}S | in {x['bought']:.2f} out {x['sold']:.2f}")
