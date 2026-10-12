# Road to BP2026 bounty thread — "Zero to Hero on DLMM" draft v2 (portfolio-anchored)
# Deadline: Oct 19-20. Target post: TODAY if assets ready, else Mon morning.
# Voice: short declaratives, no em-dashes, law endings, receipts everywhere
# Portfolio receipts (live from user's Meteora page):
#   64 closed positions | fees claimed $58.43 | win rate 48.44%
#   all-time deposit $2.54K | total PnL -$19.38 (-0.76%)
#   biggest win +$13.84 (+60.61%) | worst: HeeHaw -$27.39 (-61.72%)
#   CARDS ladder 0.235-0.282, closed today after price ran +17% past range
#   Spider: 5 launches this week with same funder in top-10 (390 wallets funded total)

## Post 1 (hook)
DLMM isn't farming. It's a ladder of limit orders that gets paid to wait.

64 closed positions later, my whole book is roughly breakeven with $58 in fees. The wins are real. The tuition was too.

Zero to hero, with the whole ledger, not just the highlights. 🧵

[IMAGE: your Meteora portfolio page screenshot, 64 positions visible]

## Post 2 (bins)
1/ Bins.

A bin is one price step. Each bin is a tiny orderbook holding your USDC or your token.

Price walks down through your bins: USDC converts to token, bin by bin. Price walks back up: token converts back, and you collected fees both directions.

You are not the farmer. You are the orderbook.

## Post 3 (range width)
2/ Range width.

Tight range (10-15 bins): more fees per dollar, more rebalancing, a part-time job.
Wide range: passive, thin, survives anything.

My winning positions were wide and boring: OWL +0.66%, CRAWL +0.38% on $1.2K over a week. My tuition was tight and impatient: -61.7% chasing a hot bin.

Bin width is a personality test. New? Go wide. Learn what a fill feels like before you optimize for it.

[IMAGE: portfolio screenshot cropped to OWL/CRAWL/HeeHaw rows]

## Post 4 (two shapes)
3/ Two shapes, two situations.

Momentum in motion, hours not days: SPOT. Even exposure across bins, upside capture, flash-dump insurance.

Waiting for a retrace, days: BID-ASK below price. You get paid to place the bids the market was going to hit anyway.

Under 4h expected = spot. Days = bid-ask. (Credit: satsmonkes' playbook, the best distillation I know.)

## Post 5 (fees)
4/ Fees.

Fees come from volume crossing your bins. Not from TVL parked.

A $700 position in a busy bin outearns $7,000 in a dead one. My monitor flags any position dead the moment its pool volume drops under $500K. It also tells me when price left my range: fees go to zero and the script says so in plain English.

Volume first. Everything else second.

[IMAGE: monitor_cards.py terminal output screenshot]

## Post 6 (entry + exit, real example)
5/ Entry and exit, one real trade.

My CARDS ladder: 0.235 to 0.282, anchored on the swing high, the major low, and the 0.5 to 0.786 retracement. Not invented. Anchored.

In range 5 days. Then price ran +17% past the top. My exit took minutes, fees near zero on the way out.

The range did its job. The recenter is the next decision, made by structure, not mood.

[IMAGE: CARDS price chart or the closed position row from portfolio]

## Post 7 (the pre-check nobody teaches)
6/ The check no guide teaches: who holds the token.

The contract can't rug you. The holders can.

This week I traced 5 fresh launches. The same funder wallet appeared in the top-10 of all 5. The newest one: a 17% holder created minutes after the pool went live. 390 wallets funded by one hand so far.

You are LPing against that. Check before you enter.

[IMAGE: graph_6Mix12Li.png funding graph]

## Post 8 (sizing + psychology)
7/ Sizing, the part that filters 95%.

My ledger: 48% win rate. Roughly breakeven. Still standing.

Size inverse to volatility. Mental stop before entry, never renegotiated in drawdown. Red day doesn't size you down. Green day doesn't size you up.

Every position is just a point. Modest greens compound. That's the whole game.

## Post 9 (the honest math)
8/ The honest math.

$2.54K deposited across 64 positions. $58.43 in fees claimed. Net PnL: -$19.38.

A 48% win rate is not failure. It is the entry fee to learning where the real edge lives: structure, patience, and checking whose money sits on the other side.

Most guides show you the winning bins. This is the whole ledger.

## Post 10 (recap + CTA)
Recap:

Bins are a ladder. Width is a choice. Volume is the boss. Anchor entries to structure. Close what runs past the range. Check the holders before any of it.

The receipts live on my timeline: diaries, monitor scripts, funding traces posted weekly.

Zero to hero is one honest position at a time. See you at Breakpoint. 🫡

---

## Asset checklist (updated for v2)
- [x] SPIDER funding graph (graph_6Mix12Li.png, ready)
- [ ] Portfolio page screenshot (64 positions, fees $58.43, win rate 48.44%) ← THE hero image, take now
- [ ] monitor_cards.py terminal output screenshot (run python3 monitor_cards.py)
- [ ] Optional: CARDS price chart showing the +17% run past your range (screenshot from dexscreener)
- [x] Entry reply posted on the bounty post (Oct 10)
- [ ] Post the thread (today or Mon 10-11 AM CT)
- [ ] Submit via lparmy.com/bounties/ca13defa-7639-41d2-b26f-50c4010cf95b
- [ ] Pin the thread
- [ ] Engage: reply to every comment in first 3h
- [ ] Comment on 3-5 other entries, genuinely

## Notes
- CWF hackathon (video + form) still first: deadline Oct 13 6:59 UTC. Bounty deadline Oct 19-20.
- Thread reuses the same receipts as the hackathon demo. One recording session serves both.
- Portfolio numbers are the moat: no other entry has a 64-position ledger to show.
