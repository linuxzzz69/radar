#!/usr/bin/env python3
"""
spider_children_seed.py — backfill spider-funded wallets into the radar watch list.

Traces top holders of the given tokens, keeps wallets first-funded by a tracked
spider, and merges them into watch_config.json (as smart watches) +
watcher_state.json (known_children). After running, the bot's child-poll loop
will ping when these wallets buy any token.

Run on the VPS (host, where the real config files live):
  cd /opt/radar && python3 spider_children_seed.py
Or with custom tokens:
  python3 spider_children_seed.py <MINT> [MINT...]

The bot live-reloads config + merges state each cycle — no restart needed.
"""
import json, sys, time, urllib.request

sys.path.insert(0, "/opt/radar" if __import__("os").path.exists("/opt/radar/watch_config.json") else ".")
from insider_radar import funder_of  # noqa: E402

SPIDERS = {
    "AgmLJBMDCqWynYnQiPCuj9ewsNNsBJyzoUhD9LJzN51": "SPIDER",
    "HckQ93Xqjjo8mwt5pNPWvyCTZXQZ858rvzmm7ZRrZg9t": "SPIDER2",
    "8k9kAKY14NzEKcHf35PpfvVoFgSDPPgTpKAL3uGukTJu": "FIGHT_BUNDLER",
}
DEFAULT_TOKENS = [
    "4FMSyEXUnXPJq7wKBVScRrCaYWPdDUNcqeuJuhC7pump",   # WIRED
    "cnNgFYRS26pKHstKvfzQXEDQuvuMfUNzTB2AMZypump",    # Playground
    "A8JUiZLzjGAsKxE74evdspHcuW4hvhPbvryDhaDZpump",   # FIGHT
    "EEmmf6uZiyMyF69nZ8BgWSuUoK1MoTNuviJjkPurpump",   # WURM
]
UA = {"User-Agent": "Mozilla/5.0"}


def top_holders(mint, n=15):
    try:
        d = json.load(urllib.request.urlopen(urllib.request.Request(
            f"https://api.rugcheck.xyz/v1/tokens/{mint}/report", headers=UA), timeout=25))
        out = []
        for h in (d.get("topHolders") or [])[:n]:
            own = h.get("owner") or ""
            pct = float(h.get("pct") or 0)
            if own and pct < 15:  # skip pool vaults / bonding curve accounts
                out.append((own, pct))
        return out
    except Exception as e:
        print(f"  holders fetch failed: {e}")
        return []


def main():
    tokens = sys.argv[1:] or DEFAULT_TOKENS
    found = {}  # wallet -> (spider_label, token_symbol)
    for mint in tokens:
        print(f"tracing {mint[:10]}...")
        for wallet, pct in top_holders(mint):
            try:
                res = funder_of(wallet)
                f = res[0] if isinstance(res, (tuple, list)) and res else None
            except Exception:
                f = None
            if f in SPIDERS:
                found[wallet] = (SPIDERS[f], mint)
                print(f"  {SPIDERS[f]}-funded: {wallet[:8]}.. ({pct:.1f}%)")
            time.sleep(0.4)
    if not found:
        print("no spider-funded holders found — nothing to seed")
        return

    # merge into watch_config.json
    cfg = json.load(open("watch_config.json"))
    watch = cfg.get("watch", [])
    have = {w["address"] for w in watch}
    for wallet, (spider, mint) in found.items():
        if wallet in have:
            continue
        watch.append({"address": wallet,
                      "label": f"{spider}_CHILD ({mint[:6]})",
                      "type": "smart", "min_sol_out": 0.1, "child_of": True})
        print(f"  + watch: {spider}_CHILD {wallet[:8]}..")
    # tighten spider funder thresholds
    for w in watch:
        if w["address"] in SPIDERS:
            w["min_sol_out"] = 0.1
    cfg["watch"] = watch
    json.dump(cfg, open("watch_config.json", "w"), indent=2)

    # merge into watcher_state.json known_children
    st = json.load(open("watcher_state.json"))
    kc = st.get("known_children", {})
    for wallet, (spider, _) in found.items():
        kc.setdefault(spider, {})[wallet] = time.strftime("%H:%M", time.gmtime())
    st["known_children"] = kc
    json.dump(st, open("watcher_state.json", "w"), indent=2)

    print(f"\nseeded {len(found)} spider children. Bot live-reloads — no restart needed.")
    print("expect 🕸️ SPIDER CHILD BUY pings with full CAs from now on.")


if __name__ == "__main__":
    main()
