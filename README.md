# Radar 🕸️

On-chain insider-detection toolkit for Solana LPs. Reads wallets, not headlines.

## What's inside

| Tool | What it does |
|---|---|
| `insider_radar.py` | Funding-ancestor tracer: pulls a token's top holders, walks each wallet back to its first-ever transaction, clusters wallets sharing a funder. Flags insider webs before you LP. |
| `watcher.py` | Live Telegram radar: watches funder wallets ("spiders"), pings when they fund fresh wallets + `/scan <CA>` command for instant token analysis (rugcheck + volume + insider trace). Runs 24/7 via systemd. |
| `monitor_cards.py` | DLMM position monitor: price vs your range, volume-health flags, dump alerts. |

## Why

LPing fresh Solana launches is donating to insiders unless you know who the insiders are. Radar finds them mechanically: not vibes, funding ancestry.

Caught in live use: one funder wallet (1,597 SOL, 20 txs in 2s) seeded top-holders across 5 trending launches in a single week.

## Usage

```bash
# trace a token's top holders to their funding ancestors
python3 insider_radar.py <TOKEN_CA> [top_n]

# run the live radar + TG bot (needs watch_config.json with bot token)
python3 watcher.py

# monitor a DLMM position
python3 monitor_cards.py
```

Requires: Python 3.10+. No API keys needed for tracing (public RPC + RugCheck + DexScreener). Telegram bot token only for the watcher.

## Config

`watch_config.json` (local only, gitignored):
```json
{
  "telegram": {"token": "...", "chat": "..."},
  "watch": [{"address": "...", "label": "SPIDER", "type": "funder", "min_sol_out": 0.5}]
}
```

## On X

Weekly scans posted publicly: [x.com/linuxz69](https://x.com/linuxz69)

Nothing here is financial advice. The contract can't rug you. The holders can.
