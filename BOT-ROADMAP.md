# Radar Bot — Future Tools Roadmap
## The complete strategy for evolving @linuxz69_radar_bot into the
## definitive Solana LP/trading intelligence terminal

**Current state (v9, deployed):** CA scan + insider trace + trade panel
+ /smart /pnl /pairs /positions /portfolio /exit /trail /sl /tp
+ spider watch + whale alerts + auto-buy + wallet custody + Docker CI/CD

**The identity:** not another BonkBot clone. The moat is the INSIDER
INTELLIGENCE layer (funding-ancestor tracing, spider detection,
serial-funder tracking) that no off-the-shelf bot has. Every future
tool doubles down on that moat while keeping the trading UX at parity.

---

## PHASE 1 — TRADING COMPLETION (Week 2)
*Finish the core loop so the terminal needs nothing else.*

### 1.1 In-chat signing completion
- Finish `jup_swap_tx` sign flow: `VersionedTransaction(vt.message, [keypair])`
  on the VPS solders 0.29 (verify version compat on deploy)
- Test: 0.05 SOL real buy -> solscan verify -> scale
- Acceptance: tap Buy 0.05 -> executed in <5s, no browser

### 1.2 Auto-buy hardening
- `/settings` interactive menu (inline buttons, edit watch_config via bot)
- Auto-buy guardrails: max daily spend, min token liquidity filter,
  blacklist mints (deny-list file), cooldown per CA
- Log every trade to `trade_history.json` (audit trail)

### 1.3 Position lifecycle
- Auto-record buys from trade txs (already done) + **auto-detect
  external sells** (token balance drops without bot action = mark position)
- PnL cards: add entry price, hold duration, peak PnL
- `/close <CA>` = sell 100% + remove position + clear SL/TP rules

---

## PHASE 2 — INTELLIGENCE DEEPENING (Weeks 2–3)
*The moat layer. Tools that answer questions nobody else can.*

### 2.1 Spider network graph (THE flagship)
- `/spiders` — list of all tracked funder wallets with their confirmed
  tokens, total SOL, child-wallet counts
- `/web <spider>` — visual text-graph of the spider's funding tree:
  ```
  SPIDER (1,597 SOL, 5 tokens)
   ├─ 9KhB..A9A -> HOOKED top-5
   ├─ 6451zSoU.. -> Chonk top-7
   └─ fresh wallet funded 2h ago -> ??? (WATCH)
  ```
- Cross-token child-wallet correlation (a child appearing in 2+
  spider-funded tokens = confirmed operator, auto-flag)
- This data becomes the weekly X thread automatically

### 2.2 Smart-money score system
- Every wallet the radar touches gets a score (0–100):
  - realized PnL history (from /smart sweeps)
  - survival across tokens (holds through dips vs dumps tops)
  - spider-adjacency penalty (funded by known spiders = suspicious)
- `/score <wallet>` shows the card
- /smart results sorted by score = "proven AND clean" wallets first

### 2.3 Launch prediction feed
- When SPIDER/SNAKE funds 2+ fresh wallets within 1h -> probability
  of incoming launch > threshold -> proactive alert: "🕸 spider
  activity spiking — watch for a launch in the next 24h"
- Historical validation: how often did spider activity precede
  launches? Track the hit rate, publish it (credibility content)

### 2.4 LP health monitor (for your DLMM positions)
- `/lp` — list your Meteora DLMM positions: in-range state, fees
  earned, distance to range edge, volume trend of the pool
- Alert when: volume drops below your floor, price approaches range
  edge, or fees/TVL ratio halves (fee fire dying)
- Uses the same monitor logic as monitor_cards.py, generalized

---

## PHASE 3 — AUTONOMY (Weeks 3–4)
*The bot starts doing work without being asked.*

### 3.1 Morning briefing (push, 9:00 AM VN daily)
Auto-posted to your chat every morning:
```
☀️ Solana ledger — [date]
ETF flows: [sign] | BTC [price] ([chg]%)
Top launch 24h: [name] ([mcap], [age]h)
Spider activity: [n] fundings in 24h
Your positions: [pnl summary]
Your alerts: [any triggered]
→ Today's watch: [top ranked fresh launch by safety score]
```
- The Daily Ledger post content AUTO-GENERATED — you review, edit
  one line, post. The 5M-impressions pipeline becomes 80% automated

### 3.2 Watch-list auto-curation
- Weekly: wallets in the watch list that went inactive 14+ days get
  flagged for removal (with their PnL summary — did following them work?)
- Suggests additions from /smart results you tapped Add on
- Keeps the watch list tight = alerts stay meaningful

### 3.3 Rug-decon series generator
- When the radar catches an insider web (like the spider thread),
  auto-draft the thread skeleton: token, holders traced, funding
  clusters, cross-token links, verdict. You add voice, post.
- The spider series becomes semi-automated without losing your voice

### 3.4 Trading journal auto-generation
- Weekly: every trade auto-summarized — wins, losses, fees paid,
  SL/TP triggers, lessons implied. Position Diary posts become
  90% pre-written

---

## PHASE 4 — THE PRODUCT (Month 2+)
*When the bot is your edge, it becomes the offer.*

### 4.1 Public tier for LP Army / Flamingos communities
- Whitelisted members get limited access: /scan + /sl /tp on their
  OWN wallets (no key custody — they import keys to their own
  instance, or a shared read-only scan tier)
- Your X thread audience converts into users; users convert into
  the contributor role you already started with Lex

### 4.2 Safety-score API for the hackathon project
- Package the DBC scanner's score as an endpoint
- Computers RH / Overload / new launches integrate = your tool
  becomes ecosystem infrastructure (the strongest contributor claim)

### 4.3 Token-gated tier
- If Flamingos or another ecosystem project launches a token,
  holding it unlocks extended bot features — aligns your tool
  with the community that promoted you

---

## BUILD PRINCIPLES (non-negotiable)
1. **Main wallet keys never touch the bot.** The hot wallet is
   separate forever. Fund only the float.
2. **Every auto-action is logged.** trade_history.json is the
   audit trail — if the bot does it, you can read it later.
3. **Alert quality > alert quantity.** Muted means muted. The
   bot's silence is trust.
4. **No token calls, ever.** The bot reports what the chain shows.
   It never says buy. That line is what makes the account credible.
5. **Push-deploy only.** Every feature lands with CI health checks.
   If the deploy fails, GitHub emails you. The pipeline is the QA.
6. **State is atomic, always.** The tmp+rename/in-place lesson is
   permanent. Any new state file uses the same save() path.

---

## PRIORITY ORDER (if time is short)
| Priority | Feature | Why |
|---|---|---|
| 1 | 1.1 in-chat signing | The terminal is half-done without it |
| 1 | 2.1 spider graph | The flagship differentiator + content engine |
| 2 | 3.1 morning briefing | Automates the 5M pipeline |
| 2 | 2.4 LP monitor | Protects your real money positions |
| 3 | 2.2 smart-money score | Upgrades /smart from list to ranked |
| 3 | 1.3 position lifecycle | Polish, not new capability |
| 4 | 3.4 journal generator | Content automation |
| 4 | 4.1 public tier | Only when the account is 5K+ |

---

## THE 30-DAY VISION
By mid-November the bot should be:
- Trading: full terminal with signing, auto-buy, SL/TP/trailing
- Intelligence: spider graph, smart-money scores, launch prediction
- Content: morning briefing auto-drafts, spider threads semi-automated
- Position: "the Robinhood Chain analyst with his own terminal"
  — the identity that the LP Army role, the Flamingos contributor
  seat, and the hackathon submission all reinforce

The bot is not a toy. It is the infrastructure of the account,
the hackathon entry, the community contribution, and eventually
the product. Every hour invested compounds across all four.
