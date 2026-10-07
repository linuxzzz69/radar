# DBC LP-Safety Scanner — v1 Spec
Project: "Radar for DBC" — hackathon submission for "Best use of Meteora DBC" ($20K, Oct 13)
Author basis: extends insider_radar.py + watcher.py (shipped, mainnet-live)

## What it does
Before an LP farms a fresh DBC launch, the scanner answers one question in 30 seconds:
**"Who really owns this token, and will they dump on my bins?"**

Output: a 0–100 Safety Score per launch, delivered as Telegram alerts, with the full funding-graph as an image + on-X summary.

## Why it fits the track (judging criteria mapping)
- **Depth of Meteora integration:** reads live DBC VirtualPool + PoolConfig accounts on-chain (program `dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN`), plus DAMM v2 post-migration pools
- **Technical execution:** production Python, VPS + systemd + CI/CD already running
- **Originality:** rugcheck tells you contract risk; this tells you *coordination* risk — the thing that actually rugs LPs on graduated launches
- **Impact:** every DBC launchpad + every LP Army member is a user
- **Traction:** built on an existing live tool with daily public scans on X

## Data sources (all public, no API keys)
1. **DBC SDK (`@meteora-ag/dynamic-bonding-curve`)** — Node service OR port via raw RPC getAccountInfo:
   - `getPoolByBaseMint(mint)` → VirtualPool address
   - VirtualPool fields: `creator`, `poolState` (curve phase / PostBondingCurve / LockedVesting / migrated), `activationPoint`, `realQuoteReserve` vs `migrationQuoteThreshold` (curve progress %), fee balances
   - `getPoolConfig(configAddress)` → PoolConfig: fee scheduler mode + params (anti-sniper decay shape), migration settings, creator fee share
2. **Solana RPC (publicnode/mainnet fallback)** — funding trace (existing engine):
   - `getSignaturesForAddress` paged back to first tx per top-holder
   - `getTransaction` v0/v1 fallback (already implemented)
3. **RugCheck API** — mint/freeze/LP-lock status (existing)
4. **DexScreener API** — volume, holders-flow, pair creation (existing)
5. **Helius/public holder listings** — top-20 token holders (existing via RugCheck report)

## The Safety Score (0–100, weighted)
| Component | Weight | How |
|---|---|---|
| Funding concentration | 30 | % of top-10 holders sharing a funding ancestor (2+ = cluster; existing radar logic) |
| Insider timing | 20 | Holder wallets created/first-funded within X hours of pool creation |
| Sniper overlap | 15 | % of first-block buyers still holding (Helius or quick tx replay of pool's first N swaps) |
| Contract basics | 15 | mint revoked, freeze none, creator balance ~0 (RugCheck) |
| Curve fairness | 10 | Anti-sniper fee decay present in PoolConfig? Migration fee sane (<20%)? |
| Liquidity health | 10 | Curve progress vs age (fair launch pace), locked-vesting configured? |

Alert tiers: 🟢 80+ | 🟡 60–79 | 🔴 <60 | ⚫ confirmed spider-linked (existing watchlist)

## Deliverables for submission
1. `dbc_scanner.py` — CLI: `python3 dbc_scanner.py <DBC_TOKEN_MINT>` → score + breakdown
2. `dbc_watch.py` — daemon: polls new DBC virtual pools (via SDK's `getPoolConfigs` / getProgramAccounts on the DBC program), auto-scans, TG alerts
3. Funding-graph image — cluster output rendered via matplotlib (deterministic layout, no external dep beyond pillow/matplotlib)
4. Public repo `linuxzzz69/radar` — open source, README, architecture diagram
5. Demo X post + 60s video walkthrough (Superteam submission needs a link + explanation)

## Build plan (6 days, VN-time evenings)
| Day | Work | Hours |
|---|---|---|
| 1 (tonight) | Repo skeleton + DBC account fetching via SDK (Node service microservice OR TypeScript rewrite of state.ts calls; simplest: small Node script `dbc_state.js` exposing JSON to Python) | 3 |
| 2 | Funding-trace integration + score engine v1 | 3 |
| 3 | Telegram alerts + watch daemon + tests on 5 real launches | 3 |
| 4 | Graph image + README + architecture diagram | 2 |
| 5 | Demo video + X thread post + submit on Superteam Earn | 3 |
| 6 (buffer) | Bug fixes, re-scan, polish | — |

## Tech decision (Day 1)
**Option A (recommended):** Node microservice `dbc_state.js` using the official SDK (TypeScript, all account layouts handled) — Python talks to it over localhost HTTP. Fast, uses official tooling = strongest "depth of integration" claim.
**Option B:** Raw Rust-free port: decode VirtualPool/PoolConfig with Python borsh by hand from the IDL. Slower (~1 day extra) but zero Node dependency.
Go with A; B is the fallback if SDK friction appears.

## Submission requirements checklist (from listing)
- [ ] GitHub repo public (or add `dannxbt` with Read access if closed)
- [ ] Built on DBC (VirtualPool/PoolConfig reads + alerts) ✓ by design
- [ ] Explanation of the build (video/thread)
- [ ] Submitted on earn.superteam.fun/listing/meteora-dbc before **Oct 13, 6:59 UTC (1:59 PM VN)**
- [ ] Mention the weekly public scans (linuxz69) as ongoing traction

## Naming
CLI: `radar-dbc` — "Scan before you farm."
