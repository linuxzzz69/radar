# CWF Track Submission — Pre-filled Form Values
(Fill in when the build is demo-ready — target Oct 11–12, deadline Oct 13 6:59 UTC)

## Link to Your Submission
A GitHub repo link (must be public-accessible):
https://github.com/linuxzzz69/radar
(final version: with dbc_scanner.py + demo README section)

## Tweet Link
The spider thread or the submission announcement post:
https://x.com/linuxz69/status/[THREAD_ID]
(paste after posting the demo thread — sponsors check this field)

## Project Name
Radar — On-chain insider detection for Solana LPs (DBC edition)
(shorter: "Radar: scan before you farm")

## Project Description
Radar makes Solana LPs measurably more profitable by answering one question in 30 seconds: who really owns this token before you farm its bins?

It reads a DBC launch's live on-chain state (VirtualPool + PoolConfig accounts on the Meteora DBC program) — curve phase, anti-sniper fee decay, migration progress — then runs a funding-ancestor trace on the token's top holders: each wallet is walked back to its first-ever transaction, and wallets sharing a funder are clustered. The result is a 0–100 LP Safety Score (funding concentration, insider timing, sniper overlap, contract basics, curve fairness, liquidity health) delivered as Telegram alerts.

In live use this week, Radar caught one funder wallet (1,597 SOL, 20 txs in 2 seconds) seeding top holders across 5 trending launches. Rugcheck tells you contract risk. Radar tells you coordination risk — the thing that actually dumps on LPs.

Built with: Meteora DBC program + SDK, Solana RPC, Python (scanner, watcher daemon, TG bot), systemd + GitHub Actions CI/CD on a live VPS.

## Project Github Link
https://github.com/linuxzzz69/radar

## Project Website
(skip or) https://github.com/linuxzzz69/radar#readme
(v2 could be a simple hosted dashboard — not needed for v1)

## Project X Link
https://x.com/linuxz69

## Pitch deck / Loom video
60–90s video: terminal recording — paste a fresh DBC token mint → score prints → funding graph renders → TG alert fires. Record with QuickTime + screen zoom. Link on YouTube (unlisted) or Loom.
https://[youtube-or-loom-link]

## Submitted to Colosseum? 
No (sidetracks are independent — per the hackathon FAQ, separate submission is fine)

## Link to Colosseum project
(skip — leave empty)

## Link to Colosseum profile
(skip — leave empty)

## Anything Else?
- Weekly public scans posted on X (x.com/linuxz69): one funder wallet tracked across 5 trending launches in a single week
- Tool is live on mainnet today: TG alerts fire on real funder activity via a VPS daemon (systemd, CI/CD)
- Open to LP Army integration — the scanner was scoped in conversation with the LP Army team
- Happy to add any DBC-specific feature the judges want demonstrated

## CHECKLIST BEFORE SUBMITTING
- [ ] dbc_scanner.py works on 5 real launches, no errors
- [ ] Score output + funding-graph image renders
- [ ] TG alert demo recorded in video
- [ ] README updated with demo section + screenshots
- [ ] Repo public, no secrets (verified: clean history)
- [ ] X thread about the build posted (for Tweet Link field)
- [ ] Video uploaded + link accessible logged-out (test in incognito!)
- [ ] Submitted BEFORE Oct 13, 6:59 UTC (1:59 PM VN) — do it Oct 11, not Oct 13
