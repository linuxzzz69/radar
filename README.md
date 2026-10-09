# Radar 🕸️ — Solana Memecoin Terminal + Insider Radar

**Scan. Trace. Trade. One Telegram bot.**

The most complete personal trading terminal on Solana: send any token CA,
get a full safety analysis with insider-tracing, then buy/sell with inline
buttons — all inside one Telegram chat. Plus the spider radar that finds
the wallets rigging launches before you touch them.

**Live on mainnet.** Dockerized, CI/CD health-checked, push-deployed.

---

## Commands

### 📊 Analysis
| Command | What it does |
|---|---|
| **Send a token CA** | Full scan: price, mcap, liquidity, volume, rugcheck, holder stats + **insider funding-trace** |
| **Paste a link** (Jupiter/GMGN/DexScreener/pump.fun) | CA auto-extracted, scanned |
| `/smart <CA>` | Find wallets with **realized profit** (bought early, sold into strength) — one-tap Add to watch list |
| `/pnl <CA>` | Position audit: is the smart money still holding? 🟢/🟡/🔴 verdict |
| `/pairs <CA>` | All LP pools compared by turnover — best venue ⭐ |
| `/new` | Fresh launches (<24h, liquidity-filtered) |
| `/mirror <wallet>` | A tracked wallet's recent buys/sells |

### 💬 Trading
| Command | What it does |
|---|---|
| **Send a CA** | Scan + trace + **trade panel** with inline buttons |
| `[Buy 0.05 / 0.1 / 0.25]` | Bot signs via Jupiter, executes instantly, tx link |
| `[Sell 25% / 50% / 100%]` | % sells, positions auto-updated |
| `/balance` | Bot wallet SOL balance |
| `/exit <CA> <pct>` | What selling X% gets right now (Jupiter-quoted) |

### 🎯 Discipline (auto-executed every 60s)
| Command | What it does |
|---|---|
| `/sl <CA> -30` | Stop-loss: auto-sell 100% at -30% |
| `/tp <CA> +100` | Take-profit: auto-sell at +100% |
| `/trail <CA> 20` | Trailing stop from peak: sell when PnL falls 20% off its high |
| `/close <CA>` | Sell 100% + clear all rules |
| `/positions` | PnL overview per holding (entry, value, %) |
| `/portfolio` | One card: wallet + positions + net worth + watch list + uptime |

### 🕸️ Insider Radar
| Command | What it does |
|---|---|
| `/add <addr> <label> <funder\|smart> [min_sol]` | Watch a wallet (funder = funding events; smart = big moves) |
| `/remove <addr>` | Stop watching |
| `/watchlist` | Tracked wallets with roles |
| `/mute` / `/unmute <addr>` | Alert toggles per wallet |
| `/mirror <wallet>` | The wallet's recent token moves |

**Passive alerts (fire automatically):**
- 🕸️ A tracked **funder** sends SOL to a fresh wallet (pre-launch signal)
- 👁 A tracked **smart wallet** makes a big move (buy/sell copy signal)
- 💓 Heartbeat every ~20h (silence = the bot died, check the VPS)

### 🤖 Admin
| Command | What it does |
|---|---|
| `/wallet` | Create the trading wallet (once) |
| `/export` | Show the private key ONCE (back it up, then delete) |
| `/status` | Radar uptime + watched wallets |
| `/settings` | Trading settings (auto-buy, presets, slippage) |
| `/help` | This menu |

---

## The insider radar (what makes this different)

Every token you scan gets **funding-ancestor tracing**: the top holders'
wallets are walked back to their first-ever transaction, and wallets
sharing a funder are clustered. One wallet funding five "independent"
top-holders across five launches is an insider web — and this tool finds
it in seconds, on-chain, without Bubblemaps.

**Live results this week:** one funder wallet (1,597 SOL, 20 txs in 2s)
seeded top-holders across 5 trending launches. Tracked automatically,
alerted via Telegram, posted publicly on X.

> The contract can't rug you. The holders can. Radar reads the holders.

---

## Setup

### Local (testing)
```bash
git clone https://github.com/linuxzzz69/radar.git
cd radar
python3 -m venv .venv && . .venv/bin/activate
pip3 install solders base58
# create watch_config.json with your Telegram bot token + chat id
python3 watcher.py
```

### Production (Docker + CI/CD)
```bash
# on the VPS:
git clone https://github.com/linuxzzz69/radar.git /opt/radar
cd /opt/radar
# place watch_config.json (telegram token/chat) + .bot_wallet.json (trading wallet)
curl -fsSL https://get.docker.com | sh
docker compose up -d
```
Full guide: [VPS-SETUP.md](VPS-SETUP.md)

**CI/CD:** every push to `master` auto-deploys to the VPS with health checks
(container running + no startup tracebacks). Failures email you via GitHub.

---

## Architecture

```
watcher.py      Telegram bot + radar loop + trade panel + callbacks
trading_bot.py  Wallet custody, Jupiter swap (sign+send), positions, SL/TP engine
insider_radar.py Funding-ancestor tracer (top holders -> first tx -> clusters)
smart_hunter.py Realized-PnL wallet hunter
monitor_cards.py DLMM position monitor
radar-dbc/      DBC launch scanner (hackathon submission)
```

- **Route:** Jupiter aggregation (all DEXes, best price, free API)
- **Signing:** solders keypair, hot wallet (fund only trading float)
- **State:** atomic writes, self-healing loads, gitignored
- **Deploy:** push to master -> GitHub Actions -> VPS -> health-verified

---

## Safety model

- The bot wallet is a **dedicated hot wallet** — fund only trading float
- Main wallet keys **never** touch this system
- Every trade passes 4 guardrails: deny-list, daily cap, balance gate, audit log
- `/export` the key once, back it up, delete the message

**Nothing here is financial advice.** The contract can't rug you.
The holders can. Radar reads the holders.
