# GMGN.AI Filter Guide — Find Good Coins
## Simple filters for finding solid memecoins to trade/hold

---

## STACK 1: SAFE COINS (for holding, swing trades)

| Filter | Setting |
|---|---|
| Liquidity | ≥ $100K |
| Volume 24h | ≥ $500K |
| Holders | ≥ 3,000 |
| Top 10 | ≤ 25% |
| Dev holding | 0% |
| Age | > 3 days |
| Smart money | ≥ 3 holding |
| Freeze/Mint | Revoked/No |
| MCAP | $1M - $50M |

**Then verify on your bot:** Send CA → trace result "no strong web" = safe.

## STACK 2: MOMENTUM PLAYS (for quick flips)

| Filter | Setting |
|---|---|
| Time | 1H |
| Volume 1H | ≥ $200K |
| 1H change | +20% to +200% |
| Liquidity | ≥ $50K |
| Top 10 | ≤ 30% |
| Dev | 0% |
| Age | < 24h |
| Smart money | ≥ 2 buying |

**Then verify on your bot:** /smart <CA> → if smart money exited = late, skip.

## AVOID (red flags)

- ❌ Top 10 > 40% (whale dump risk)
- ❌ Dev holding > 0%
- ❌ Volume < $50K/hour
- ❌ Snipers > 20%
- ❌ Bundled (GMGN badge)
- ❌ MCAP < $100K
- ❌ Holder count dropping
- ❌ 1H volume > 24H volume (one-candle pump)

---

## HEART ATTACK SPECIFIC (when market conditions are right)

## THE HEART ATTACK FILTER STACK (your primary need)

### GMGN → Trending → Solana → apply these filters:

| Filter | Setting | Why |
|---|---|---|
| **Time** | 1H or 6H (not 24H) | Heart Attack is a NOW strategy — 24H data hides dead tokens |
| **Volume** | **≥ $100K** (1H basis) | molu's minimum: "High volume is necessary for success; aim for 100K-1M" |
| **Liquidity** | **≥ $50K** | Below this, your bins ARE the pool — you're the exit door |
| **MCap** | **$500K – $5M** | The sweet spot: big enough for real flow, small enough for volatility |
| **Holder count** | **≥ 1,000** | Below this = chat group, not community |
| **Top 10 holders** | **≤ 30%** | Above this = someone can dump through your bins instantly |
| **Dev holding** | **0%** | Non-negotiable |
| **Age** | **< 24h** for Heart Attack targets | Fresh = fresh DLMM pool with active liquidity |
| **DEX** | **Meteora DLMM** (check the pool type) | PumpSwap-only tokens can't run Heart Attack |

### THEN verify on your bot (3 checks):

1. **Send the CA to your bot** → scan + rugcheck + insider trace
2. **Check `/pairs <CA>`** → compare pools, find the DLMM venue
3. **Run `/heart-attack <CA>`** → if the pool has liquidity, size buttons appear

If `/heart-attack` shows the panel → ALL conditions met → tap 0.05 SOL.

---

## THE SAFETY FILTER STACK (for spot trades / general research)

### GMGN → New Pairs → Solana → apply these:

| Filter | Setting |
|---|---|
| **Safety score** | GMGN's built-in rugcheck badge (green only) |
| **Dev holding** | 0% |
| **Top 10** | ≤ 25% |
| **Smart money** | ≥ 3 tracked wallets holding |
| **Snipers** | ≤ 15% of first 100 buys |
| **Freeze/Mint** | revoked/no |
| **Liquidity** | ≥ $80K (post-graduation) |
| **Volume** | ≥ $50K/hour |
| **Holders** | ≥ 2,000 (growing, not flat) |

### THEN verify on your bot:

```
Send CA → your bot runs:
  1. DexScreener: price/mcap/liq/vol
  2. RugCheck: mint/freeze/top holders
  3. Insider trace: funding ancestors
  4. /smart <CA>: who actually profited
  5. /pnl <CA>: are they still in?
```

---

## THE COPY-TRADE FILTER (find wallets to /add to your radar)

### GMGN → Leaderboard → apply these:

| Filter | Setting |
|---|---|
| **PnL (30d)** | > $100K |
| **Win rate** | > 60% |
| **Trade size** | $5K+ (not dust traders) |
| **Active** | last trade < 24h ago |
| **Tokens traded** | 5–30 (not 200+ — that's a bot) |

### THEN verify with your bot:

```
/mirror <wallet> → recent moves
/add <wallet> <label> smart 1.0 → auto-alerts on their trades
```

---

## THE ZOMBIE POOL DETECTOR (avoid Heart Attack failures)

Before running /heart-attack on ANY token, check:

1. **GMGN → Token page → Pools tab** — look for Meteora DLMM pools
2. **Check the pool's "Liquidity Distribution" chart** on meteora.ag:
   - If the active price has bins around it with liquidity = **GOOD**
   - If the active price is FAR from the liquidity bins = **ZOMBIE**
3. **On meteora.ag, check "24h Volume"** for the specific DLMM pool:
   - If the DLMM pool has $0-5K volume but the token shows high volume → the volume is on PumpSwap/Raydium, not Meteora

### Quick zombie check on your bot:

```
/pairs <CA>
```
If the DLMM pool has tiny volume vs the PumpSwap pool → the Heart Attack won't work there.

---

## GMGN PAGE NAVIGATION MAP

| Tab | Use for |
|---|---|
| **Trending** | Heart Attack targets (highest current volume) |
| **New Pairs** | Early plays + insider detection |
| **Leaderboard** | Wallet discovery for your radar |
| **Copy Trading** | Following smart money |
| **Wallet Tracker** | After you /add someone |

### GMGN-specific tools to use:
1. **"Holding Period"** on wallet profiles — shows if they hold or flip
2. **"Token PnL"** on wallet profiles — per-token profit breakdown
3. **"Bundle Detection"** — shows if the launch was pre-loaded

---

## YOUR COMPLETE WORKFLOW

```
GMGN filter pass → 3-5 candidates → paste CA in bot → bot verifies:
  scan / trace / pairs check → if DLMM pool has liquidity:
    /heart-attack <CA> → tap 0.05 → PnL card → /sl /tp /trail → withdraw when happy
  → if not: spot trade or skip
```

---

## WHEN TO CHECK (Vietnam time)

| Time (VN) | Market condition | Best for |
|---|---|---|
| **7–9 PM** | US morning opens | Heart Attack targets (LPs redeploy) |
| **10 PM–1 AM** | US midday peak | Copy trades, watch alerts |
| **2–6 AM** | Post-close lull | Research, Playground practice |
| **9 AM–12 PM** | EU overlap | Check overnight alerts, post Ledger |

---

## FINAL NOTE

Your bot already automates what GMGN does manually:
- Scan = GMGN trending (but with YOUR safety scoring)
- Trace = GMGN wallet analysis (but with YOUR funding-ancestor detection)
- Pairs = GMGN pool comparison (but with turnover ranking)
- /smart = GMGN leaderboard (but with realized-PnL verification)

The GMGN filter stack is your **discovery layer**.
Your bot is your **verification layer**.
Together they are the complete workflow.
