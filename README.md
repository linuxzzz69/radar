# Radar-DBC 🕸️

**Scan before you farm.** LP safety scoring for Meteora DBC launches.

Part of [Radar](https://github.com/linuxzzz69/radar) — on-chain insider detection for Solana LPs.
Submission: "Best use of Meteora DBC" — Crypto World's Fair sidetrack.

## What it does
Before an LP farms a fresh DBC token, Radar answers in 30 seconds: **who really owns this token?**

1. Reads the launch's live DBC state on-chain — `VirtualPool` + `PoolConfig` from the official SDK (`dbc_state.js` microservice): curve phase, anti-sniper fee config, migration progress
2. Traces the token's top holders back to their **first-ever transactions** and clusters wallets sharing a funding ancestor (`dbc_scanner.py`)
3. Prints a **0–100 LP Safety Score** with a per-component breakdown

## Live example
EMBER launch (graduated DBC pool): scored **84/100 🟢** — no funding clusters, contract clean, curve complete. Real output from mainnet today.

In live use this week, Radar's engine caught one funder wallet (1,597 SOL, 20 txs in 2s) seeding top-holders across **5 trending launches**.

## Architecture
```
dbc_state.js   (Node, official @meteora-ag/dynamic-bonding-curve-sdk)
  └─ HTTP :8077 /state?mint=  → VirtualPool + PoolConfig JSON
dbc_scanner.py (Python)
  ├─ fetches DBC state from :8077
  ├─ funding trace via insider_radar.py engine (RPC, first-tx ancestry)
  ├─ RugCheck contract basics + DexScreener flows
  └─ weighted score: funding 30 | timing 20 | snipers 15 | contract 15 | curve 10 | liquidity 10
```

## Run
```bash
# 1. start the DBC state service
npm install
node dbc_state.js          # needs RPC_URL env if mainnet-beta rate-limits you

# 2. score any DBC launch
python3 dbc_scanner.py <TOKEN_BASE_MINT>
```

## The stack
- `@meteora-ag/dynamic-bonding-curve-sdk` (official Meteora SDK)
- Solana JSON-RPC (public), RugCheck, DexScreener
- Python 3.10+, Node 18+

Nothing here is financial advice. The contract can't rug you. The holders can. Radar reads the holders.

## Trading module (bot v4)

The Telegram bot can create a dedicated trading wallet (`/wallet`), export its key once (`/export`), and show buy/sell panels on every CA scan. Wallet keys are local files (0600, gitignored).

VPS setup for trading:
```bash
cd /opt/radar && python3 -m venv .venv
.venv/bin/pip install solders base58
```
