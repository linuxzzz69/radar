# satsmonkes LP Playbook — Distilled for Our Strategy
Source: "The LP playbook Meteora: every DLMM setup I actually run, and why"
(https://x.com/satsmonkes/status/2085463469277716899 — Meteora mod, 12,891
positions since May 2024, "Milord" DLMM class in LP Army)

## Core philosophy
1. **Volume is the priority. Everything else serves it.** Chase turnover,
   not TVL (validates our fee-density screening).
2. Memecoin TA patterns repeat at high frequency — train on memecoins,
   apply everywhere. Pattern speed = reps.
3. Take frameworks, not signals. "What matters isn't running the exact
   same range, it's understanding why the range exists."

## The 4 setups (his book)

### Setup 1 — Single-sided SOL TIGHT range (top blast play)
- When: first bullish leg, real volume + genuine hype, top of the move
- How: 10–15 bins, 15-second timeframe, micro-rebound fee harvesting
- In/out within minutes ("heart attack" setups — 14% in minutes)
- Prerequisite: hotkeys/muscle memory BEFORE real size
- Our take: this is the endgame skill. Skip for now (we don't have the
  execution speed or capital). Watch for him doing it = learn visually.

### Setup 2 — Single-sided SOL BID-ASK wide range (Fibonacci DCA)
- When: post-ATH retrace play on a token with structure
- How: Fib from ATH→major low; place bid-ask from ~0.5 to ~0.786 retrace
- The self-fulfilling prophecy: the whole market bids at 0.382/0.5/0.618/0.786
- Real example: $SISYPUSS — bid-ask pinned at ~75% below ATH / 0.7 fib zone,
  closed +36.48% in 10h, $740 TVL exploratory size
- KEY INSIGHT: "You never had to predict anything. You just had to be there
  with size, at the prices the collective market had already decided."
- Our take: THIS is the upgrade to our CARDS bid-only playbook. Our -2%/-17%
  spot ladder should become a FIB-anchored bid-ask (0.5→0.786 of the swing).

### Setup 3 — Single-sided SOL SPOT (momentum frame)
- When: <4h duration, first-hours memecoin, bullish leg IN MOTION
- Why spot: even exposure across bins = more upside capture + flash-dump
  insurance (no single-bin overload)
- His framework line: "Short duration + bullish momentum = SPOT.
  Longer duration + waiting for retrace = Bid-Ask."
- Our take: we've been doing this correctly (CARDS spot bid). But he holds
  fees in the fee token during momentum = adds upside exposure.

### Setup 4 — BID-ASK FLIP (the two-phase engine)
Phase 1: quote-asset bid-ask below price → fills token on the dump + fees
Phase 2: structure turns (higher low, sell-volume dries) → FLIP the range
above price, now single-sided token = distribution engine selling the bag
Phase 3: fees again on the way up. Two fee collections, one position.
- Signal to flip: "boring but effective": sellers exhausted, no new lows,
  volume drying on down-candles, first higher low on 15m/1h
- Real example: $ANSEM — Day 1: +$290 PnL, $124 fees (mostly SOL still).
  Day 2: -15% dump filled him to ~50/50, fees $341 (+$217 on panic volume).
  Day 3: flip → closed +$1,112 (+4.55%, 2d23h). PLUS a parallel USDC bid-ask
  on same coin: +$597 (+3.98%, 5d18h). Combined ~$1,700 on one conviction.
- Our take: this is the natural evolution of our bid-only playbook. When our
  CARDS ladder fills and the higher-low prints — flip instead of holding.

## Psychology / bankroll (the part that filters 95%)
- **"It's just a point"** (Federer rule): every position is independent.
  Red day ≠ size down. Green day ≠ size up. Play the aggregate.
- **Sizing rule: inverse to volatility, inverse to conviction gap.**
  Biggest positions on high-conviction mature structure. Fresh unknown
  memecoin = small + treat as tuition. (We inverted this once — the
  Cartridge chase — now codified.)
- **Mental stop decided BEFORE opening.** Never renegotiate in drawdown.
- **Modest greens compound.** +$100/+$500/+$1000 closes = a book.
- **Bear market = the filter.** Whoever keeps process in dead volume
  auto-wins the turn.

## Direct upgrades to OUR strategy
1. **CARDS bid → Fib-anchored bid-ask.** Anchor: recent swing ATH→low.
   Place 0.5→0.786, not arbitrary -2%/-17%. Same capital, market-coherent
   levels, fees during the walk-in.
2. **The flip as our exit plan.** Our current plan says "if filled, decide
   consciously." Upgrade: the decision is now codified — higher low + dry
   down-volume on 15m/1h = flip the range above price, sell the bag into
   the reflow. Write it into monitor_cards.py as a state.
3. **Duration selector:** <4h expected = spot. Days = bid-ask. Our
   overnight HYPE/SOL both-sided fits; EMBER bid fits (days).
4. **Sizing codified:** EMBER $3.60 (low conviction, fresh-ish) ✓ correct.
   CARDS re-entry should be sized UP vs exploratory plays ✓ consistent.
5. **Fee-token holding during momentum legs** (his Setup 3 detail) —
   optional micro-edge, costs nothing.
6. **The "just a point" rule goes in reply-style.md** — our account's
   psychological doctrine aligns; quote it when we post the position diary.

## Content angles unlocked (for the 5M plan)
- "I read the Milord playbook so you don't have to" thread (12K+ views
  potential — his audience + LP Army overlap)
- Position Diary format upgrade: log flips, not just fills
- The spider thread gets a new chapter: setup 1 (tight-range top-blast)
  is EXACTLY what spider wallets front-run — our radar detects the
  pre-positioning that makes top-blasting dangerous for retail
