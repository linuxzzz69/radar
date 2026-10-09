#!/usr/bin/env python3
"""
watcher.py - linuxz69 on-chain radar + Telegram bot
Usage: python3 ~/Desktop/x/watcher.py   (runs forever; Ctrl+C to stop)

PASSIVE RADAR:
  - funding-parents: alert when they send SOL to NEW wallets (pre-launch signal)
  - smart-money wallets: alert on big SOL moves

INTERACTIVE (send to the bot chat):
  <token CA>          -> full scan: rugcheck + volume + insider funding-trace
  <wallet address>    -> quick wallet look
  /status             -> radar uptime + watched list
  /add <addr> <label> <funder|smart> [min_sol]   -> add watch (live)
  /remove <addr>      -> remove watch
  /help

Config: watch_config.json   State: watcher_state.json
"""
import json, time, urllib.request, urllib.parse, os, re, threading
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(BASE, "watch_config.json")
STATE_PATH = os.path.join(BASE, "watcher_state.json")
POLL_SECONDS = 90
RPC = "https://solana-rpc.publicnode.com"
RPC2 = "https://api.mainnet-beta.solana.com"
UA = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
BASE58 = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
START_TS = time.time()

def load(p, default):
    if os.path.exists(p):
        try:
            with open(p) as f: return json.load(f)
        except json.JSONDecodeError:
            # corrupt (e.g. interleaved writes from two processes) - back it up, start fresh
            try: os.rename(p, p + ".corrupt." + str(int(time.time())))
            except Exception: pass
            return default
    return default

def save(p, obj):
    # NOTE: p may be a Docker-mounted file (single-file bind mount).
    # os.replace()/rename over a bind-mount target raises EBUSY, so we
    # write in-place with a process-local lock to avoid interleaved writes.
    import threading
    global _save_lock
    try:
        _save_lock
    except NameError:
        _save_lock = threading.Lock()
    with _save_lock:
        tmp = p + ".tmp"
        with open(tmp, "w") as f:
            json.dump(obj, f, indent=1)
        try:
            os.replace(tmp, p)          # works on normal paths
        except OSError:
            # bind-mounted file: rewrite in place instead of renaming
            with open(p, "w") as f:
                json.dump(obj, f, indent=1)
            try: os.remove(tmp)
            except Exception: pass

def rpc(method, params, url=RPC):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, data=body, headers=UA)
            r = json.load(urllib.request.urlopen(req, timeout=20))
            if "error" in r:
                if r["error"].get("code") == 429:
                    time.sleep(2 + attempt * 2); continue
                return None
            return r.get("result")
        except Exception:
            time.sleep(1 + attempt)
    return rpc(method, params, RPC2) if url == RPC else None

def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return json.load(urllib.request.urlopen(req, timeout=25))

def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def tg_send(token, chat, text):
    data = urllib.parse.urlencode({"chat_id": chat, "text": text, "parse_mode": "HTML",
                                   "disable_web_page_preview": "true"}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data), timeout=15)
    except Exception as e:
        print("tg send failed:", e)

def tx_details(sig):
    for ver in (0, 1):
        for url in (RPC, RPC2):
            body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getTransaction",
                               "params": [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": ver}]}).encode()
            try:
                req = urllib.request.Request(url, data=body, headers=UA)
                r = json.load(urllib.request.urlopen(req, timeout=20)).get("result")
                if r: return r
            except Exception:
                continue
            time.sleep(0.3)
    return None

def summarize_transfer(tx):
    if not tx: return None
    msg = tx["transaction"]["message"]
    keys = [k["pubkey"] if isinstance(k, dict) else k for k in msg["accountKeys"]]
    meta = tx.get("meta") or {}
    pre = meta.get("preBalances") or []
    post = meta.get("postBalances") or []
    if len(pre) != len(post) or not pre: return None
    deltas = [(keys[i], (b - a) / 1e9) for i, (a, b) in enumerate(zip(pre, post))
              if i < len(keys) and abs(b - a) >= 1_000_000]
    # SPL token deltas per owner (detect token buys/sells)
    # NOTE: some balances have no "owner" (use accountIndex) - skip those safely
    tok_delta = {}
    for b in (meta.get("preTokenBalances") or []):
        o = b.get("owner")
        if not o: continue
        tok_delta.setdefault(o, {})["pre"] = (b.get("mint") or "", int(b["uiTokenAmount"]["amount"]))
    for b in (meta.get("postTokenBalances") or []):
        o = b.get("owner")
        if not o: continue
        mint = b.get("mint") or ""
        amt = int(b["uiTokenAmount"]["amount"])
        e = tok_delta.setdefault(o, {})
        if "pre" in e and e["pre"][0] == mint:
            d = amt - e["pre"][1]
            if d != 0: e["tok_delta"] = (mint, d)
        else:
            e["tok_delta"] = (mint, amt)
    token_moves = [(str(o), v["tok_delta"][0], v["tok_delta"][1])
                   for o, v in tok_delta.items() if "tok_delta" in v]
    return {"fee_payer": keys[0], "deltas": deltas, "token_moves": token_moves,
            "sig_full": tx.get("transaction", {}).get("signatures", [None])[0], "err": meta.get("err")}

# ---------------- token analysis ----------------

def dex_summary(ca):
    try:
        d = get_json(f"https://api.dexscreener.com/latest/dex/tokens/{ca}")
        ps = d.get("pairs") or []
        p = max(ps, key=lambda x: (x.get("liquidity") or {}).get("usd", 0)) if ps else None
        if not p: return None
        v, pc = p.get("volume") or {}, p.get("priceChange") or {}
        tx = (p.get("txns") or {}).get("h24", {})
        vol24, vol1h = v.get("h24") or 0, v.get("h1") or 0
        fresh = " ⚠️ALL VOL <1h" if vol24 and vol1h and vol1h > 0.7 * vol24 else ""
        return {"dex": p.get("dexId"), "price": p.get("priceUsd"),
                "mcap": (p.get("marketCap") or 0), "liq": (p.get("liquidity") or {}).get("usd") or 0,
                "vol24": vol24, "vol1h": vol1h, "fresh": fresh,
                "h1": pc.get("h1"), "h24": pc.get("h24"),
                "buys": tx.get("buys"), "sells": tx.get("sells"),
                "symbol": (p.get("baseToken") or {}).get("symbol"), "pair": p.get("pairAddress")}
    except Exception:
        return None

def rug_summary(ca):
    try:
        d = get_json(f"https://api.rugcheck.xyz/v1/tokens/{ca}/report")
        th = d.get("topHolders") or []
        ins = [h for h in th if h.get("insider")]
        cr = d.get("creatorBalance", 0); tot = (d.get("token") or {}).get("supply", 0) or 1
        return {"mint": "revoked" if not d.get("mintAuthority") else "MINTABLE!",
                "freeze": "YES!" if d.get("freezeAuthority") else "no",
                "top1": th[0]["pct"] if th else 0,
                "top10": sum(h["pct"] for h in th[:10]),
                "insiders": len(ins), "creator": 100 * cr / tot,
                "holders": d.get("totalHolders"), "rugged": d.get("rugged"),
                "report": d}
    except Exception:
        return None

def insider_trace(ca, rug, top_n=8):
    """Funding-trace top holders (reuses insider_radar functions)."""
    import insider_radar as IR
    pools = set()
    try:
        d = get_json(f"https://api.dexscreener.com/latest/dex/tokens/{ca}")
        pools = {p["pairAddress"] for p in (d.get("pairs") or []) if p.get("pairAddress")}
    except Exception:
        pass
    holders = [h for h in (rug.get("topHolders") or []) if h.get("pct", 0) > 0.3]
    holders = [h for h in holders if (h.get("owner") or h.get("address")) not in pools][:top_n]
    results = []
    for h in holders:
        owner = h.get("owner") or h.get("address")
        if not owner: continue
        fp, _ = IR.funder_of(owner)
        results.append({"owner": owner, "pct": h["pct"], "funder": fp})
        time.sleep(0.4)
    byf = defaultdict(list)
    for r in results:
        if r["funder"] and r["funder"] != r["owner"]:
            byf[r["funder"]].append(r)
    clusters = {f: rs for f, rs in byf.items() if len(rs) >= 2}
    lines = []
    for f, rs in sorted(clusters.items(), key=lambda kv: -len(kv[1])):
        tot = sum(r["pct"] for r in rs)
        lines.append(f"🕸 FUNDER <code>{f[:8]}..{f[-4:]}</code> -> {len(rs)} wallets = {tot:.1f}% supply")
    linked = sum(len(rs) for rs in clusters.values())
    verdict = (f"⚠️ <b>INSIDER WEB: {linked}/{len(results)} top holders linked</b>"
               if linked >= 3 else f"✅ no strong web ({linked}/{len(results)} linked)")
    return ("\n".join(lines) if lines else "(no shared funders among top holders)"), verdict

def analyze_token(tg, chat, ca, top_n=8):
    dex, rug = dex_summary(ca), rug_summary(ca)
    if not dex and not rug:
        tg_send(tg["token"], chat, f"❌ <code>{ca[:12]}..</code> — no DexScreener/RugCheck data. Invalid CA?")
        return
    # (trade panel with inline buttons sent separately after the scan)
    if dex:
        s = dex
        msg = (f"🔍 <b>{esc(s['symbol'])}</b> | {esc(s['dex'])}\n"
               f"price ${s['price']} | mcap ${s['mcap']/1e3:,.0f}K | liq ${s['liq']/1e3:,.0f}K\n"
               f"vol24 ${s['vol24']/1e3:,.0f}K (1h: ${s['vol1h']/1e3:,.0f}K){esc(s['fresh'])}\n"
               f"1h {s['h1']}% | 24h {s['h24']}% | buys {s['buys']} / sells {s['sells']}\n")
    else:
        s, msg = None, f"🔍 <code>{ca[:10]}..</code>\n"
    if rug:
        msg += (f"🛡 mint: {rug['mint']} | freeze: {rug['freeze']} | rugged: {rug['rugged']}\n"
                f"top1 {rug['top1']:.1f}% | top10 {rug['top10']:.1f}% | "
                f"insiders {rug['insiders']} | creator {rug['creator']:.2f}% | holders {rug['holders']}\n")
    if dex and (dex['vol24'] or 0) < 50_000:
        msg += "⚠️ volume under $50K — radar signal weak\n"
    msg += "\n🧵 tracing funding ancestors (top %d)..." % top_n
    tg_send(tg["token"], chat, msg)
    try:
        detail, verdict = insider_trace(ca, rug or {}, top_n)
        tg_send(tg["token"], chat, f"🧵 <b>TRACE RESULT</b>\n{detail}\n{verdict}")
    except Exception as e:
        tg_send(tg["token"], chat, f"🧵 trace failed: {e}")
    send_trade_panel(tg, chat, ca)


def mirror_wallet(tg, chat, wallet):
    """Show a watched wallet's recent token buys/sells from tx history."""
    tg_send(tg["token"], chat, f"👁 mirroring <code>{wallet[:8]}..</code> last moves...")
    import urllib.request
    UA2 = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
    def rpc(m, p):
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode()
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request("https://api.mainnet-beta.solana.com", data=body, headers=UA2), timeout=25))
            return r.get("result")
        except Exception:
            return None
    sigs = rpc("getSignaturesForAddress", [wallet, {"limit": 12}]) or []
    moves = []
    for s in sigs[:12]:
        if s.get("err"): continue
        tx = rpc("getTransaction", [s["signature"], {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])
        time.sleep(0.3)
        if not tx: continue
        meta = tx.get("meta") or {}
        if meta.get("err"): continue
        ts = time.strftime("%m-%d %H:%M", time.gmtime(s.get("blockTime") or 0))
        ptb2 = meta.get("postTokenBalances") or []
        ptb = meta.get("preTokenBalances") or []
        pre = {}
        for b in ptb:
            o = b.get("owner")
            if o: pre.setdefault(o, {})[b.get("mint","")] = int(b["uiTokenAmount"]["amount"])
        post = {}
        for b in ptb2:
            o = b.get("owner")
            if o: post.setdefault(o, {})[b.get("mint","")] = int(b["uiTokenAmount"]["amount"])
        mints = set(list(pre.get(wallet, {}).keys()) + list(post.get(wallet, {}).keys()))
        for m in mints:
            d = post.get(wallet, {}).get(m, 0) - pre.get(wallet, {}).get(m, 0)
            if abs(d) > 1000:
                side = "BOUGHT" if d > 0 else "SOLD"
                moves.append(f"{ts} | {side} {abs(d)/1e6:.1f}M of {m[:6]}..{m[-4:]}")
    if moves:
        tg_send(tg["token"], chat, "👁 <b>MIRROR — last moves</b>\n" + "\n".join(moves[:10]))
    else:
        tg_send(tg["token"], chat, "no token moves found in recent history")



def fresh_launches(tg, chat):
    """Last fresh Solana launches with quick safety verdicts."""
    tg_send(tg["token"], chat, "🕸 scanning fresh launches...")
    try:
        dd = get_json("https://api.dexscreener.com/latest/dex/search?q=solana%20pump")
        ps = dd.get("pairs") or []
        fresh = []
        now = time.time() * 1000
        for p in ps:
            if p.get("chainId") != "solana": continue
            b = (p.get("baseToken") or {})
            if b.get("symbol") in ("SOL","WSOL","USDC"): continue
            liq = (p.get("liquidity") or {}).get("usd") or 0
            v24 = (p.get("volume") or {}).get("h24") or 0
            created = p.get("pairCreatedAt") or 0
            age_h = (now - created) / 3600000
            if liq < 15_000 or age_h > 24: continue
            fresh.append((age_h, b.get("symbol"), b.get("address"),
                          round((p.get("marketCap") or 0)/1e3),
                          round(liq/1e3), round(v24/1e3),
                          (p.get("priceChange") or {}).get("h24")))
        fresh.sort()
        if not fresh:
            tg_send(tg["token"], chat, "no fresh launches above liquidity floor")
            return
        body = "\n".join(f"{s} | {age}h | mcap ${mc}K | liq ${lq}K | vol ${v}K | {chg}%"
                          for _, s, _, mc, lq, v, chg in fresh[:8])
        tg_send(tg["token"], chat,
                f"🕸 <b>FRESH LAUNCHES (&lt;24h)</b>\n{body}\n\n"
                f"Send any CA for the full scan + insider trace.")
    except Exception as e:
        tg_send(tg["token"], chat, f"fresh scan failed: {e}")




def pnl_audit(tg, chat, ca):
    """Position audit: price vs the smart money's cost basis."""
    tg_send(tg["token"], chat, "📊 auditing position...")
    try:
        import smart_hunter
        winners, pool = smart_hunter.hunt(ca, sample=30)
        dd = get_json(f"https://api.dexscreener.com/latest/dex/tokens/{ca}")
        ps = dd.get("pairs") or []
        best = max(ps, key=lambda x:(x.get('liquidity') or {}).get('usd',0)) if ps else None
        px = best.get('priceUsd') if best else '?'
        sym = (best.get('baseToken') or {}).get('symbol','?') if best else '?'
        if not winners:
            tg_send(tg["token"], chat,
                    f"📊 <b>{sym} AUDIT</b>\nprice ${px}\n"
                    f"no realized-PnL wallets found in the window - either very early,\n"
                    f"or volume is too thin to judge. Careful.")
            return
        # are the realized winners still holding? that's the answer
        from insider_radar import rpc as _rpc
        holding = 0
        for w in winners[:5]:
            res = _rpc("getTokenAccountsByOwner",[w["wallet"],{"mint":ca},{"encoding":"jsonParsed"}])
            time.sleep(0.3)
            still = False
            if res:
                for a in res.get("result",{}).get("value",[]):
                    info=a["account"]["data"]["parsed"]["info"]
                    if int(info["tokenAmount"]["amount"])>0: still=True; break
            holding += 1 if still else 0
        tg_send(tg["token"], chat,
                f"📊 <b>{sym} AUDIT</b>\nprice ${px}\n"
                f"realized-PnL wallets: {len(winners)}\n"
                f"still holding after profit: {holding}/{min(len(winners),5)}\n"
                f"{'🟢 smart money is IN - the run may have legs' if holding>=3 else '🟡 mixed' if holding>=1 else '🔴 smart money already exited - be careful'}")
    except Exception as e:
        tg_send(tg["token"], chat, f"audit failed: {e}")



def portfolio_card(tg, chat):
    """One card: positions + watch list + uptime."""
    try:
        cfg2 = load(CFG_PATH, {}) or {}
        from trading_bot import load_positions, position_pnl, load_wallet, sol_balance
        _, pub = load_wallet()
        sol = sol_balance(pub)
        d = load_positions()
        lines=[]
        net = sol
        for mint,p in d.items():
            if p["tokens"]<=0: continue
            r=position_pnl(mint)
            if not r: continue
            sym,val,pnl_sol,pnl_pct,_=r
            net+=val
            lines.append(f"{'🟢' if pnl_pct>=0 else '🔴'} {sym}: {pnl_pct:+.1f}% ({pnl_sol:+.4f} SOL)")
        wl=cfg2.get("watch",[])
        up=(time.time()-START_TS)/3600
        body="\n".join(lines) if lines else "(no open positions)"
        tg_send(tg["token"], chat,
                f"📒 <b>PORTFOLIO</b>\n"
                f"💰 wallet: {sol:.3f} SOL\n"
                f"📈 positions:\n{body}\n"
                f"➖ net worth: {net:.3f} SOL\n"
                f"👁 watching {len(wl)} wallets\n"
                f"⏱ uptime {up:.1f}h")
    except Exception as e:
        tg_send(tg["token"], chat, f"portfolio error: {e}")



def exit_calc(tg, chat, ca, pct):
    """Show what selling X% gets right now, before executing."""
    try:
        from trading_bot import token_balance
        bal = token_balance(pub0(), ca) if False else None
        # use bot wallet
        from trading_bot import load_wallet
        _, pub = load_wallet()
        bal = token_balance(pub, ca)
        if bal <= 0:
            tg_send(tg["token"], chat, "no holding of that token")
            return
        dd = get_json(f"https://api.dexscreener.com/latest/dex/tokens/{ca}")
        ps = dd.get("pairs") or []
        best = max(ps, key=lambda x:(x.get('liquidity') or {}).get('usd',0)) if ps else None
        px = float(best.get('priceUsd') or 0) if best else 0
        sym = (best.get('baseToken') or {}).get('symbol','?') if best else '?'
        raw = int(bal * pct / 100)
        q = None
        try:
            q = json.load(urllib.request.urlopen(urllib.request.Request(
                f"https://lite-api.jup.ag/swap/v1/quote?inputMint={ca}&outputMint=So11111111111111111111111111111111111111112&amount={raw}&slippageBps=1500",
                headers={"User-Agent":"Mozilla/5.0"}), timeout=20))
        except Exception:
            pass
        got = int(q.get("outAmount", 0))/1e9 if q and q.get("outAmount") else None
        usd = got * 115 if got else raw/1e6 * px * 1e6 / 1e6 * 1e0
        usd = got * 115.0 if got else None
        line = f"you'd get ~{got:.4f} SOL (~${usd:.2f})" if got else "no route right now"
        tg_send(tg["token"], chat,
                f"🚪 <b>EXIT CALC</b> — sell {pct}% of {sym}\n"
                f"holding {bal/1e6:.1f}M\n{line}\n"
                f"(tap Sell {pct}% in the panel to execute)")
    except Exception as e:
        tg_send(tg["token"], chat, f"exit calc error: {e}")


def smart_feed(tg, chat, ca):
    """Find wallets with realized profit on a token - then offer /add."""
    tg_send(tg["token"], chat, "🧠 hunting profitable wallets...")
    try:
        import smart_hunter
        winners, pool = smart_hunter.hunt(ca)
        if not winners:
            tg_send(tg["token"], chat,
                    "🧠 <b>SMART HUNT</b>\nno wallets with realized profit found in the sampled window\n"
                    "(try later: RPC rate limits or too few trades)")
            return
        body = "\n".join(
            f"🧠 <code>{w['wallet']}</code>\n"
            f"net <b>+{w['net_sol']} SOL</b> | {w['buys']}B/{w['sells']}S"
            for w in winners[:5])
        # /add buttons for the top 3
        from trading_bot import wallet_exists
        rows = [[("➕ Add", f"addsmart:{w['wallet']}")] for w in winners[:3]]
        tg_buttons(tg["token"], chat,
                f"🧠 <b>SMART HUNT — realized PnL wallets</b>\n{body}\n\nTap to add to your watch list:",
                rows)
    except Exception as e:
        tg_send(tg["token"], chat, f"smart hunt failed: {e}")

def pairs_compare(tg, chat, ca):
    """All pools for a token, side by side, best LP pool marked."""
    tg_send(tg["token"], chat, "🔍 comparing pools...")
    try:
        dd = get_json(f"https://api.dexscreener.com/latest/dex/tokens/{ca}")
        ps = dd.get("pairs") or []
        rows = []
        for p in sorted(ps, key=lambda x: -((x.get('liquidity') or {}).get('usd') or 0))[:6]:
            liq = (p.get('liquidity') or {}).get('usd') or 0
            vol = (p.get('volume') or {}).get('h24') or 0
            to = round(vol/liq,1) if liq else 0
            b=(p.get('baseToken') or {}); q=(p.get('quoteToken') or {})
            rows.append((to, f"{b.get('symbol')}/{q.get('symbol')} {p.get('dexId')} | "
                          f"liq ${round(liq/1e3)}K | vol24 ${round(vol/1e6,2)}M | TO {to}x | "
                          f"<code>{p.get('pairAddress','')[:10]}..</code>"))
        rows.sort(reverse=True)
        body = "\n".join(("⭐ " if i==0 else "   ")+r[1] for i,r in enumerate(rows))
        tg_send(tg["token"], chat, f"🔍 <b>POOLS for this token (best turnover first)</b>\n{body}\n\n⭐ = recommended LP venue")
    except Exception as e:
        tg_send(tg["token"], chat, f"pairs failed: {e}")

def watchlist_show(tg, chat):
    cfg2 = load(CFG_PATH, {}) or {}
    wl = cfg2.get("watch", [])
    if not wl:
        tg_send(tg["token"], chat, "watch list empty. /add <addr> <label> <funder|smart>")
        return
    body = "\n".join(f"• {w['label']} <code>{w['address'][:8]}..{w['address'][-4:]}</code> ({w['type']}, ≥{w.get('min_sol_out',0.5)} SOL)"
                      for w in wl)
    tg_send(tg["token"], chat, f"👁 <b>WATCH LIST ({len(wl)})</b>\n{body}")

def handle_command(tg, chat, text, state):
    text = text.strip()
    if text.startswith("/help") or text == "/start":
        tg_send(tg["token"], chat,
                "🤖 <b>linuxz69 radar</b>\n"
                "Send a token CA -> scan + trace + trade panel\n"
                "Send a wallet -> quick look\n"
                "/wallet - create trading wallet (once)\n"
                "/export - show private key ONCE (backup it!)\n"
                "/balance - bot wallet SOL balance\n"
                "/status - radar health\n"
                "/add <addr> <label> <funder|smart> [min_sol]\n"
                "/remove <addr>\n"
                "/new - fresh launches (<24h)\n"
                "/mirror <wallet> - recent moves of a tracked wallet\n"
                "/sl <CA> <pct> - stop-loss (auto-sell at -pct%)\n"
                "/tp <CA> <pct> - take-profit (auto-sell at +pct%)\n"
                "/positions - PnL overview\n"
                "/smart <CA> - find realized-PnL wallets\n"
                "/pnl <CA> - position audit (smart money status)\n"
                "/exit <CA> <pct> - what selling X% gets right now\n"
                "/trail <CA> <pct> - trailing stop from peak\n"
                "/portfolio - full book card\n"
                "/mute /unmute <wallet> - alert toggles\n"
                "(paste a jup/gmgn/dexscreener link - CA auto-extracted)\n"
                "/pairs <CA> - compare LP pools\n"
                "/watchlist - tracked wallets\n"
                "/help - this menu\n"
                "⚠️ trading wallet = hot wallet. Fund only what you can lose.")
    elif text.startswith("/wallet"):
        try:
            from trading_bot import create_wallet, wallet_exists, load_wallet
        except ImportError as ie:
            tg_send(tg["token"], chat,
                    f"⚠️ trading module needs setup on the server:\n"
                    f"pip3 install solders base58 --break-system-packages\n"
                    f"then: systemctl restart radar\n({ie})")
            return
        if wallet_exists():
            _, pub = load_wallet()
            tg_send(tg["token"], chat, f"✅ wallet already exists\n📍 <code>{pub}</code>\nFund it with SOL to enable buys.")
        else:
            r = create_wallet()
            tg_send(tg["token"], chat,
                    f"🆕 <b>Trading wallet created</b>\n📍 <code>{r['pubkey']}</code>\n\n"
                    f"1. Fund it with SOL (send from your main wallet)\n"
                    f"2. Then send any CA to trade\n"
                    f"3. /export to back up the private key ONCE")
    elif text.startswith("/export"):
        try:
            from trading_bot import load_wallet
            kp, pub = load_wallet()
            import base58 as b58
            priv = b58.b58encode(bytes(kp)).decode()
            tg_send(tg["token"], chat,
                    f"🚨 <b>PRIVATE KEY — BACK THIS UP NOW, THEN DELETE THIS MESSAGE</b>\n\n"
                    f"<code>{priv}</code>\n\n"
                    f"Anyone with this key owns the wallet. Save it in a password "
                    f"manager or write it on paper. Never share. Never screenshot.")
        except Exception as e:
            tg_send(tg["token"], chat, "no wallet yet. /wallet first")
    elif text.startswith("/exit "):
        try:
            p=text.split()
            ca2, pct = p[1], int(p[2]) if len(p)>2 else 100
            threading.Thread(target=exit_calc, args=(tg, chat, ca2, pct), daemon=True).start()
        except Exception as e:
            tg_send(tg["token"], chat, f"usage: /exit <CA> <pct> ({e})")
    elif text == "/portfolio":
        portfolio_card(tg, chat)
    elif text.startswith("/positions"):
        try:
            from trading_bot import positions_overview, load_wallet
            lines, net = positions_overview()
            _, pub = load_wallet()
            if not lines:
                tg_send(tg["token"], chat, f"📍 <code>{pub[:8]}..</code>\nno open positions. Send a CA to buy.")
                return
            import base58 as b58
            from trading_bot import token_balance
            body = "\n".join(lines)
            tg_send(tg["token"], chat, f"📊 <b>Positions Overview</b>\n\n{body}\n\nNet: {net:.4f} SOL")
        except Exception as e:
            tg_send(tg["token"], chat, f"positions error: {e}")
    elif text.startswith("/settings"):
        cfg2 = load(CFG_PATH, {})
        t = cfg2.get("trading", {})
        tg_send(tg["token"], chat,
                f"⚙️ <b>Trading settings</b>\n"
                f"auto-buy on CA: {'ON' if t.get('autobuy') else 'OFF'}\n"
                f"buy preset: {t.get('preset_sol', 0.05)} SOL\n"
                f"slippage: {t.get('slippage_bps', 1500)/100:.1f}%\n"
                f"(edit watch_config.json 'trading' block + restart to change)")
    elif text.startswith("/pnl "):
        try:
            ca2 = text.split()[1]
            threading.Thread(target=pnl_audit, args=(tg, chat, ca2), daemon=True).start()
        except Exception as e:
            tg_send(tg["token"], chat, f"usage: /pnl <CA> ({e})")
    elif text.startswith("/smart "):
        try:
            ca2 = text.split()[1]
            threading.Thread(target=smart_feed, args=(tg, chat, ca2), daemon=True).start()
        except Exception as e:
            tg_send(tg["token"], chat, f"usage: /smart <CA> ({e})")
    elif text.startswith("/pairs "):
        try:
            ca2 = text.split()[1]
            threading.Thread(target=pairs_compare, args=(tg, chat, ca2), daemon=True).start()
        except Exception as e:
            tg_send(tg["token"], chat, f"usage: /pairs <CA> ({e})")
    elif text == "/watchlist":
        watchlist_show(tg, chat)
    elif text == "/new":
        threading.Thread(target=fresh_launches, args=(tg, chat), daemon=True).start()
    elif text.startswith("/mute ") or text.startswith("/unmute "):
        w = text.split()[1]
        cfg2 = load(CFG_PATH, {}) or {}
        for x in cfg2.get("watch", []):
            if x["address"] == w:
                x["muted"] = text.startswith("/mute")
                save(CFG_PATH, cfg2)
                state_txt = "MUTED" if x["muted"] else "UNMUTED"
                tg_send(tg["token"], chat, f"👁 {x['label']} {state_txt}")
                return
        tg_send(tg["token"], chat, "wallet not in watch list")
    elif text.startswith("/mirror "):
        try:
            w = text.split()[1]
            threading.Thread(target=mirror_wallet, args=(tg, chat, w), daemon=True).start()
        except Exception as e:
            tg_send(tg["token"], chat, f"usage: /mirror <wallet> ({e})")
    elif text.startswith("/trail "):
        try:
            parts = text.split()
            mint, pct = parts[1], float(parts[2])
            from trading_bot import set_rule, load_positions
            d = load_positions()
            if mint not in d:
                tg_send(tg["token"], chat, "no position in that token")
                return
            set_rule(mint, "trail", pct)
            tg_send(tg["token"], chat,
                    f"🎯 Trailing stop set: {mint[:8]}.. trails {pct:.1f}% from peak.\n"
                    f"Bot sells 100% when PnL falls {pct:.1f}% below its highest point.")
        except Exception as e:
            tg_send(tg["token"], chat, f"usage: /trail <CA> 20 ({e})")
    elif text.startswith("/sl ") or text.startswith("/tp "):
        kind = "sl" if text.startswith("/sl") else "tp"
        try:
            parts = text.split()
            mint, pct = parts[1], float(parts[2])
            from trading_bot import set_rule, load_positions
            d = load_positions()
            if mint not in d:
                tg_send(tg["token"], chat, "no position in that token. /positions to see open ones")
                return
            set_rule(mint, kind, pct)
            label = "STOP LOSS" if kind == "sl" else "TAKE PROFIT"
            tg_send(tg["token"], chat,
                    f"🎯 {label} set: {mint[:8]}.. at {pct:+.1f}%\n"
                    f"The bot will auto-sell 100% when PnL crosses it.\n"
                    f"(checked every 60s)")
        except Exception as e:
            tg_send(tg["token"], chat, f"usage: /sl <CA> -30  or  /tp <CA> 100 ({e})")
    elif text.startswith("/balance"):
        try:
            from trading_bot import load_wallet, sol_balance
            _, pub = load_wallet()
            sol = sol_balance(pub)
            tg_send(tg["token"], chat, f"📍 <code>{pub}</code>\n💰 SOL: {sol:.4f}")
        except Exception:
            tg_send(tg["token"], chat, "no wallet yet. /wallet first")
    elif text.startswith("/status"):
        cfg = load(CFG_PATH, {})
        up = (time.time() - START_TS) / 3600
        st = load(STATE_PATH, {})
        w = "\n".join(f"• {x['label']} <code>{x['address'][:6]}..{x['address'][-4:]}</code>"
                      for x in cfg.get("watch", []))
        tg_send(tg["token"], chat, f"📡 <b>radar status</b>\nuptime: {up:.1f}h\nwatching {len(cfg.get('watch', []))}:\n{w}")
    elif text.startswith("/add "):
        parts = text.split()
        if len(parts) < 4 or parts[3] not in ("funder", "smart"):
            tg_send(tg["token"], chat, "usage: /add <addr> <label> <funder|smart> [min_sol]")
            return
        addr, label, typ = parts[1], parts[2], parts[3]
        entry = {"address": addr, "label": label, "type": typ,
                 "min_sol_out": float(parts[4]) if len(parts) > 4 else (0.5 if typ == "funder" else 1.0)}
        cfg = load(CFG_PATH, {})
        cfg["watch"] = [x for x in cfg.get("watch", []) if x["address"] != addr]
        cfg["watch"].append(entry)
        save(CFG_PATH, cfg)
        tg_send(tg["token"], chat, f"✅ now watching {label} <code>{addr[:8]}..</code> ({typ})")
    elif text.startswith("/remove "):
        addr = text.split()[1]
        cfg = load(CFG_PATH, {})
        cfg["watch"] = [x for x in cfg.get("watch", []) if x["address"] != addr]
        save(CFG_PATH, cfg)
        tg_send(tg["token"], chat, f"🗑 removed <code>{addr[:8]}..</code>")
    elif ("jup.ag" in text or "dexscreener.com" in text or "gmgn.ai" in text
          or "pump.fun" in text or "meteora.ag" in text):
        # extract mint from URL-style paste
        import re as _re
        m2 = _re.search(r"(?:tokens|token|swap[/SOL-]*|dlmm[/]|pairs[/solana/])/?([1-9A-HJ-NP-Za-km-z]{32,44})", text)
        if not m2:
            m2 = _re.search(r"([1-9A-HJ-NP-Za-km-z]{40,44}pump)", text)
        if not m2:
            m2 = _re.search(r"([1-9A-HJ-NP-Za-km-z]{43,44})", text)
        if m2:
            ca2 = m2.group(1)
            tg_send(tg["token"], chat, f"🔎 extracted CA: <code>{ca2}</code>")
            handle_command(tg, chat, ca2, state)
        else:
            tg_send(tg["token"], chat, "couldn't find a token address in that link. Send the raw CA.")
    elif BASE58.match(text):
        cfg_w = load(CFG_PATH, {}) or {}
        watched = {w["address"] for w in cfg_w.get("watch", [])}
        if text in watched:
            tg_send(tg["token"], chat,
                    f"👁 <code>{text[:8]}..{text[-4:]}</code> is a <b>watched wallet</b>, not a token CA.\n"
                    f"Send a token contract address to scan/trade. This wallet is on your watch list.")
            return
        threading.Thread(target=analyze_token, args=(tg, chat, text), daemon=True).start()
        def send_trade_panel(ca):
            try:
                from trading_bot import wallet_exists, load_wallet, sol_balance
                import json as _json
                cfg_t = (load(CFG_PATH, {}) or {}).get("trading", {})
                if not wallet_exists():
                    tg_buttons(tg["token"], chat,
                            "⚡ <b>TRADE PANEL</b> — no wallet yet.",
                            [[("🔧 Setup Wallet", "wallet:setup")]])
                    return
                _, pub = load_wallet()
                sol = sol_balance(pub)
                if cfg_t.get("autobuy") and sol >= float(cfg_t.get("preset_sol", 0.05)) + 0.02:
                    preset = float(cfg_t.get("preset_sol", 0.05))
                    tg_send(tg["token"], chat, f"⏳ auto-buying {preset} SOL of <code>{ca[:8]}..</code> ...")
                    from trading_bot import do_buy, record_buy
                    sig, err = do_buy(ca, preset)
                    if err:
                        tg_send(tg["token"], chat, f"❌ auto-buy failed: {err}")
                    else:
                        try:
                            dd = get_json(f"https://api.dexscreener.com/latest/dex/tokens/{ca}")
                            best = max(dd.get("pairs") or [], key=lambda x:(x.get('liquidity') or {}).get('usd',0))
                            sym = (best.get('baseToken') or {}).get('symbol','?')
                        except Exception:
                            sym = '?'
                        record_buy(ca, sym, preset, 0)
                        tg_send(tg["token"], chat,
                                f"✅ <b>AUTO-BOUGHT</b> {preset} SOL of {sym}\n"
                                f"tx: https://solscan.io/tx/{sig}\n/positions for PnL")
                    return
                if sol < 0.06:
                    tg_buttons(tg["token"], chat,
                            f"⚡ <b>TRADE PANEL</b> — <code>{pub[:8]}..</code>\n💰 {sol:.3f} SOL — fund this address, then tap Buy.",
                            [[("🟢 Buy 0.05", f"buy:0.05:{ca}"), ("🟢 Buy 0.1", f"buy:0.1:{ca}"), ("🟢 Buy 0.25", f"buy:0.25:{ca}")],
                             [("🔧 /balance", "balance:check")]])
                    return
                tg_buttons(tg["token"], chat,
                        f"⚡ <b>TRADE PANEL</b> — <code>{pub[:8]}..</code> ({sol:.3f} SOL)\nTap a button — the bot signs and executes instantly.",
                        [[("🟢 Buy 0.05", f"buy:0.05:{ca}"), ("🟢 Buy 0.1", f"buy:0.1:{ca}"), ("🟢 Buy 0.25", f"buy:0.25:{ca}")],
                         [("🔴 Sell 25%", f"sell:25:{ca}"), ("🔴 Sell 50%", f"sell:50:{ca}"), ("🔴 Sell 100%", f"sell:100:{ca}")]])
            except Exception as e:
                tg_send(tg["token"], chat, f"trade panel error: {e}")
        threading.Thread(target=send_trade_panel, args=(text,), daemon=True).start()
    else:
        tg_send(tg["token"], chat, "🤔 not a command. Send a Solana CA or /help")


def tg_buttons(token, chat, text, buttons, reply_to=None):
    """buttons: list of (label, callback_data)"""
    kb = {"inline_keyboard": [[{"text": l, "callback_data": c} for (l, c) in row]
                               for row in buttons]}
    data = urllib.parse.urlencode({"chat_id": chat, "text": text, "parse_mode": "HTML",
                                   "reply_markup": json.dumps(kb)}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data), timeout=15)
    except Exception as e:
        print("tg buttons failed:", e)

def tg_answer_callback(token, cb_id, text=None):
    data = urllib.parse.urlencode({"callback_query_id": cb_id, "text": text or ""}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"https://api.telegram.org/bot{token}/answerCallbackQuery", data=data), timeout=10)
    except Exception:
        pass

def handle_callback(tg, chat, cb_id, data):
    """data format: buy:<amount>:<ca>  or  sell:<pct>:<ca>"""
    st = load(STATE_PATH, {})
    seen_cbs = st.get("seen_callbacks", [])
    if cb_id in seen_cbs:
        return  # dedupe Telegram retries
    seen_cbs.append(cb_id)
    st["seen_callbacks"] = seen_cbs[-50:]
    save(STATE_PATH, st)
    tg_answer_callback(tg["token"], cb_id, "executing...")
    try:
        parts = data.split(":")
        action, val = parts[0], parts[1]
        ca = parts[2] if len(parts) > 2 else None
        if action == "wallet":
            handle_command(tg, chat, "/wallet", None)
            return
        if action == "balance":
            handle_command(tg, chat, "/balance", None)
            return
        if action == "addsmart":
            wallet_addr = val
            cfg2 = load(CFG_PATH, {})
            cfg2["watch"] = [x for x in cfg2.get("watch", []) if x["address"] != wallet_addr]
            cfg2["watch"].append({"address": wallet_addr, "label": "SMART", "type": "smart", "min_sol_out": 0.5})
            save(CFG_PATH, cfg2)
            tg_send(tg["token"], chat, f"✅ SMART wallet added to watch list")
            return
        if action == "jupbuy":
            handle_callback(tg, chat, cb_id, f"buy:{val}:{ca}")
            return
        from trading_bot import wallet_exists, load_wallet, do_buy, do_sell, token_balance
        if not wallet_exists():
            tg_send(tg["token"], chat, "❌ no trading wallet. /wallet first")
            return
        if action == "buy":
            amt = float(val)
            tg_send(tg["token"], chat, f"⏳ buying {amt} SOL of <code>{ca[:8]}..</code> ...")
            kp, pub = load_wallet()
            from trading_bot import do_buy, sol_balance as _sol_balance
            sig, err = do_buy(ca, amt)
            if err and "insufficient" in str(err):
                kp2, pub2 = load_wallet()
                bal = _sol_balance(pub2)
                tg_buttons(tg["token"], chat,
                        f"💰 <b>Fund the wallet to enable trading</b>\n"
                        f"<code>{pub2}</code>\n"
                        f"balance: {bal:.3f} SOL — send 0.1-0.2 SOL from your main,\n"
                        f"then tap Buy again. One-time fuel, then one-tap trading.",
                        [[("🔄 /balance", "balance:check")]])
                return
            if err:
                tg_send(tg["token"], chat, f"❌ buy failed: {err}")
            else:
                tg_send(tg["token"], chat,
                        f"✅ <b>BOUGHT</b> {amt} SOL of <code>{ca[:8]}..</code>\n"
                        f"tx: https://solscan.io/tx/{sig}\n"
                        f"/balance to check")
        elif action == "sell":
            pct = int(val)
            tg_send(tg["token"], chat, f"⏳ selling {pct}% of <code>{ca[:8]}..</code> ...")
            from trading_bot import do_sell
            sig, err = do_sell(ca, pct)
            if err:
                tg_send(tg["token"], chat, f"❌ sell failed: {err}")
            else:
                from trading_bot import record_sell
                record_sell(ca, pct)
                tg_send(tg["token"], chat,
                        f"✅ <b>SOLD</b> {pct}% of <code>{ca[:8]}..</code>\n"
                        f"tx: https://solscan.io/tx/{sig}\n"
                        f"/positions for PnL")
    except Exception as e:
        tg_send(tg["token"], chat, f"trade error: {e}")



def tg_edit(token, chat, msg_id, text):
    data = urllib.parse.urlencode({"chat_id": chat, "message_id": msg_id,
                                   "text": text, "parse_mode": "HTML"}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"https://api.telegram.org/bot{token}/editMessageText", data=data), timeout=15)
    except Exception:
        pass  # message unchanged or too old - fine

def pnl_poll_loop(tg, chat):
    """Every 60s: edit PnL cards in place + check SL/TP rules."""
    while True:
        time.sleep(60)
        try:
            from trading_bot import load_positions, position_pnl, load_card, get_rules, load_wallet, do_sell, sol_balance
            d = load_positions()
            for mint, p in list(d.items()):
                if p["tokens"] <= 0: continue
                r = position_pnl(mint)
                if not r: continue
                sym, val_sol, pnl_sol, pnl_pct, tokens = r
                usd = tokens * (best_price_usd(mint) or 0)
                card = load_card(mint)
                if card:
                    tg_edit(tg["token"], card["chat"], card["msg"],
                            f"📊 <b>{sym}</b> LIVE — PnL {pnl_pct:+.1f}% ({pnl_sol:+.4f} SOL)\n"
                            f"Value: ${usd:.2f}\nSell via buttons below ⬇")
                # SL/TP check
                rules = get_rules(mint)
                do_sell_now = False
                reason = ""
                if "sl" in rules and pnl_pct <= float(rules["sl"]):
                    do_sell_now, reason = True, f"STOP LOSS {pnl_pct:.1f}% <= {rules['sl']}%"
                if "tp" in rules and pnl_pct >= float(rules["tp"]):
                    do_sell_now, reason = True, f"TAKE PROFIT {pnl_pct:.1f}% >= {rules['tp']}%"
                # trailing stop: once in profit, trail the peak. Track peak in state.
                if "trail" in rules and pnl_pct > 0:
                    st_pnl = load(STATE_PATH, {})
                    peak = st_pnl.get("trails", {}).get(mint, {"peak": 0})
                    pk = max(peak.get("peak", 0), pnl_pct)
                    if pnl_pct <= pk - float(rules["trail"]):
                        do_sell_now, reason = True, f"TRAILING STOP: peaked {pk:.1f}%, fell to {pnl_pct:.1f}% (trail {rules['trail']}%)"
                        st_pnl.setdefault("trails", {}).pop(mint, None)
                        save(STATE_PATH, st_pnl)
                    else:
                        tr = st_pnl.setdefault("trails", {})
                        if tr.get(mint, {}).get("peak", 0) < pk:
                            tr[mint] = {"peak": pk}
                            save(STATE_PATH, st_pnl)
                if do_sell_now:
                    kp, pub = load_wallet()
                    from trading_bot import do_sell as _ds
                    sig, err = _ds(mint, 100)
                    if err:
                        tg_send(tg["token"], chat, f"⚠️ {reason} — sell failed: {err}")
                    else:
                        from trading_bot import record_sell
                        record_sell(mint, 100)
                        tg_send(tg["token"], chat,
                                f"🎯 <b>{reason} — AUTO-SOLD 100%</b>\n"
                                f"tx: https://solscan.io/tx/{sig}")
        except Exception as e:
            print("pnl_poll error:", e)

def best_price_usd(mint):
    try:
        from trading_bot import get_json
        dd = get_json(f"https://api.dexscreener.com/latest/dex/tokens/{mint}")
        ps = dd.get("pairs") or []
        best = max(ps, key=lambda x: (x.get("liquidity") or {}).get("usd", 0)) if ps else None
        return float(best["priceUsd"]) if best else 0
    except Exception:
        return 0

def tg_listener(tg, chat):
    offset = load(STATE_PATH, {}).get("tg_offset", 0)
    while True:
        try:
            url = f"https://api.telegram.org/bot{tg['token']}/getUpdates?offset={offset}&timeout=0"
            ups = json.load(urllib.request.urlopen(urllib.request.Request(url), timeout=15)).get("result", [])
            for u in ups:
                offset = u["update_id"] + 1
                if "callback_query" in u:
                    cb = u["callback_query"]
                    cid = (cb.get("message") or {}).get("chat", {}).get("id")
                    cdata = cb.get("data") or ""
                    cbid = cb.get("id")
                    if str(cid) == str(chat) and cdata:
                        threading.Thread(target=handle_callback, args=(tg, chat, cbid, cdata), daemon=True).start()
                    st2 = load(STATE_PATH, {})
                    st2["tg_offset"] = u["update_id"] + 1
                    save(STATE_PATH, st2)
                    offset = u["update_id"] + 1
                    continue
                m = u.get("message") or {}
                cid = (m.get("chat") or {}).get("id")
                txt = m.get("text") or ""
                if str(cid) == str(chat) and txt:
                    handle_command(tg, chat, txt, None)
                    st = load(STATE_PATH, {})
                    st["tg_offset"] = offset
                    save(STATE_PATH, st)
        except Exception as e:
            print("tg_listener:", e); time.sleep(5)
        time.sleep(3)

# ---------------- passive radar ----------------

def radar_loop(tg, chat):
    cfg = load(CFG_PATH, None)
    if cfg is None:
        cfg = {"telegram": {"token": tg["token"], "chat_id": chat, "chat": chat},
               "watch": [{"address": "AgmLJBMDCqWynYnQiPCuj9ewsNNsBJXyzoUhD9LJzN51",
                          "label": "SPIDER (serial funder)", "type": "funder", "min_sol_out": 0.5}]}
        save(CFG_PATH, cfg)
    state = load(STATE_PATH, {"seen": {}, "known_children": {}})
    seen = defaultdict(dict, state.get("seen", {}))
    known_children = state.get("known_children", {})
    last_heartbeat = time.time()

    print(f"radar watching {len(cfg['watch'])}, poll {POLL_SECONDS}s. Ctrl+C to stop.")
    # NOTE: no startup broadcast message - duplicates on every restart annoyed the user.
    # Status visible via /status in Telegram.


    while True:
        cfg = load(CFG_PATH, cfg)   # live-reload config (picks up /add //remove)
        for w in cfg.get("watch", []):
            if w.get("muted"): continue
            addr, typ = w["address"], w["type"]
            res = rpc("getSignaturesForAddress", [addr, {"limit": 30}])
            if not res: continue
            fresh = [s for s in res if not s.get("err") and s["signature"] not in seen.get(addr, {})]
            for s in res:
                seen.setdefault(addr, {})[s["signature"]] = s.get("blockTime") or 0
            if len(seen[addr]) > 500:
                seen[addr] = dict(sorted(seen[addr].items(), key=lambda kv: -kv[1])[:300])
            save(STATE_PATH, {"seen": seen, "known_children": known_children,
                              "tg_offset": load(STATE_PATH, {}).get("tg_offset", 0)})

            for s in fresh[:6]:
                info = summarize_transfer(tx_details(s["signature"]))
                if not info or info["err"]: continue
                if typ == "funder":
                    fundings = [d for k, d in info["deltas"] if d < -w.get("min_sol_out", 0.5) and k == addr]
                    if not fundings: continue
                    recips = [(k, d) for k, d in info["deltas"] if d > w.get("min_sol_out", 0.5) and k != addr]
                    for rk, rd in recips[:4]:
                        is_new = rk not in known_children.get(addr, {})
                        known_children.setdefault(addr, {})[rk] = time.strftime("%H:%M", time.gmtime(s.get("blockTime", 0)))
                        icon = "🕸️ NEW" if is_new else "🔁"
                        tg_send(tg["token"], chat,
                                f"{icon} <b>{w['label']}</b> funded child\n"
                                f"💰 {rd:.2f} SOL -> <code>{rk[:8]}..{rk[-6:]}</code>\n"
                                f"https://solscan.io/tx/{s['signature']}")
                        print(f"alert: {icon} {rd:.2f} SOL -> {rk[:8]}..")
                elif typ == "smart":
                    sig_full = info.get("sig_full") or s["signature"]
                    # token side of the trade for the watched wallet
                    tok_info = ""
                    for (owner, mint, delta) in info.get("token_moves", []):
                        if owner == addr and abs(delta) > 0:
                            side = "BOUGHT" if delta > 0 else "SOLD"
                            tok_info = f"{side} {abs(delta)/1e6:.1f}M of {mint[:6]}..{mint[-4:]}"
                            break
                    for k, d in info["deltas"]:
                        if k == addr and abs(d) >= w.get("min_sol_out", 1.0):
                            tag = "BUY" if d < 0 else "SELL"
                            body_txt = tok_info if tok_info else f"{d:+.2f} SOL moved"
                            tg_send(tg["token"], chat,
                                    f"👁 <b>{w['label']}</b> {tag}\n"
                                    f"{body_txt}\n"
                                    f"SOL delta: {d:+.2f}\n"
                                    f"https://solscan.io/tx/{sig_full}")
                            print(f"alert: {w['label']} {tag} {d:+.2f} {tok_info}")
            time.sleep(1.5)
        if time.time() - last_heartbeat > 20 * 3600:
            last_heartbeat = time.time()
            tg_send(tg["token"], chat, f"💓 radar alive — {len(cfg.get('watch', []))} watched, "
                                       f"uptime {(time.time()-START_TS)/3600:.1f}h")
        time.sleep(POLL_SECONDS)

def main():
    cfg = load(CFG_PATH, {}) or {}
    tg = cfg.get("telegram") or {}
    token = tg.get("token") or os.environ.get("TG_TOKEN")
    chat = tg.get("chat") or tg.get("chat_id")
    if not token or not chat:
        print("missing telegram token/chat in", CFG_PATH); sys.exit(1)
    threading.Thread(target=tg_listener, args=(tg, chat), daemon=True).start()
    threading.Thread(target=pnl_poll_loop, args=(tg, chat), daemon=True).start()
    radar_loop(tg, chat)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nstopped.")
