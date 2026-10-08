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
        with open(p) as f: return json.load(f)
    return default

def save(p, obj):
    with open(p, "w") as f: json.dump(obj, f, indent=1)

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
    tok_delta = {}
    for b in (meta.get("preTokenBalances") or []):
        o = b.get("owner")
        if o: tok_delta.setdefault(o, {})["pre"] = (b.get("mint"), int(b["uiTokenAmount"]["amount"]))
    for b in (meta.get("postTokenBalances") or []):
        o = b.get("owner")
        if o:
            mint, amt = b.get("mint"), int(b["uiTokenAmount"]["amount"])
            e = tok_delta.setdefault(o, {})
            if "pre" in e and e["pre"][0] == mint:
                d = amt - e["pre"][1]
                if abs(d) > 0: e["tok_delta"] = (mint, d)
            else:
                e["tok_delta"] = (mint, amt)
    token_moves = [(o, v[0], v[1]) for o, v in tok_delta.items() if "tok_delta" in v]
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
    # Jupiter quick-trade links (wallet signs, bot never holds keys)
    buy_05 = f"https://jup.ag/swap/SOL-{ca}?amount=0.05"
    buy_10 = f"https://jup.ag/swap/SOL-{ca}?amount=0.1"
    sell_link = f"https://jup.ag/swap/{ca}-SOL"
    trade_block = (
        f"\n⚡ <b>Quick Trade</b> (opens Jupiter, YOUR wallet signs):\n"
        f"🟢 <a href=\"{buy_05}\">Buy 0.05 SOL</a> | "
        f"<a href=\"{buy_10}\">Buy 0.1 SOL</a>\n"
        f"🔴 <a href=\"{sell_link}\">Sell (pick % in Jupiter)</a>\n"
    )
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
    msg += trade_block
    msg += "\n🧵 tracing funding ancestors (top %d)..." % top_n
    tg_send(tg["token"], chat, msg)
    try:
        detail, verdict = insider_trace(ca, rug or {}, top_n)
        tg_send(tg["token"], chat, f"🧵 <b>TRACE RESULT</b>\n{detail}\n{verdict}")
    except Exception as e:
        tg_send(tg["token"], chat, f"🧵 trace failed: {e}")

def handle_command(tg, chat, text, state):
    text = text.strip()
    if text.startswith("/help") or text == "/start":
        tg_send(tg["token"], chat,
                "🤖 <b>linuxz69 radar</b>\n"
                "Send a token CA -> full scan + insider trace\n"
                "Send a wallet -> quick look\n"
                "/status - radar health\n"
                "/add <addr> <label> <funder|smart> [min_sol]\n"
                "/remove <addr>\n"
                "/help - this menu")
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
    elif BASE58.match(text):
        threading.Thread(target=analyze_token, args=(tg, chat, text), daemon=True).start()
    else:
        tg_send(tg["token"], chat, "🤔 not a command. Send a Solana CA or /help")

def tg_listener(tg, chat):
    offset = load(STATE_PATH, {}).get("tg_offset", 0)
    while True:
        try:
            url = f"https://api.telegram.org/bot{tg['token']}/getUpdates?offset={offset}&timeout=0"
            ups = json.load(urllib.request.urlopen(urllib.request.Request(url), timeout=15)).get("result", [])
            for u in ups:
                offset = u["update_id"] + 1
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

    tg_send(tg["token"], chat,
            "🟢 <b>linuxz69 radar online</b>\n"
            + "\n".join(f"• {w['label']} <code>{w['address'][:6]}..{w['address'][-4:]}</code> ({w['type']})"
                        for w in cfg["watch"]))
    print(f"radar watching {len(cfg['watch'])}, poll {POLL_SECONDS}s. Ctrl+C to stop.")

    while True:
        cfg = load(CFG_PATH, cfg)   # live-reload config (picks up /add //remove)
        for w in cfg.get("watch", []):
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
    radar_loop(tg, chat)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nstopped.")
