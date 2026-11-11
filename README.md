# Brooks ES Paper-Trading Replication

Paper-trading research: replicating Al Brooks' E-mini price-action
decisions with a small rule engine (v2 / v3), scored against dense
oral ground truth recovered from Brooks Trading Course daily reviews.

## What's in here (all our own work)

- `engines/brooks-intraday-engine-v2.py` — v2 intraday engine
- `engines/brooks-intraday-engine-v3.py` — v3 engine (frozen 2026-11-04,
  used for Period 2: S2 depth gate ≥8 pts, S2 structural stop,
  late-session weak-S3 gate)
- `engines/backtest-prev5-intraday-engine.py` — backtest harness
- `docs/brooks-v3-rules-and-period2-2026-11-04.md` — v3 rules + Period 2 setup
- `docs/brooks-casebook-v1-2026-11-10.md` — casebook v1 report (312
  bar-anchored decision points, 6 days)
- `data/casebook-v1.json` — casebook v1 data: classification only
  (date / bar / family / direction / oral timestamp). No transcript text.
- `docs/brooks-replication-v2-2026-10-16-22.md` — v2 replication report
- `docs/brooks-1020-oral-vs-text-measured-2026-10-28.md` — oral-vs-text
  density measurement (2026-10-20)
- `docs/brooks-learning-todo-plan-2026-11-10.md` — 5-stage learning plan

## What's deliberately NOT in here

- Brooks video transcripts (`brooks-*-transcript.txt` / `.pdf`) — the
  narrator's spoken words are course content; not republished.
- Ground-truth JSONs (`replication-ground-truth*.json`) — they carry
  short verbatim quotes; each item needs a de-sensitisation pass
  before any of it can go public.
- Engine decision/trade logs and portfolio ledgers — internal working
  files; add later only if the owner wants them public.

## Results so far (2026-11-11)

- Period 1 (v2): $10,000 → $9,719.00 (−$281.00).
- Period 2 (v3, 5 US sessions 11-04–11-10): 5 trades, 2 wins,
  $10,000 → $10,116.75 (+$116.75). S3 2/2 (+$277.25), S1 0/3
  (−$160.50), S2: 0 trades in Period 2 — its depth gate / structural
  stop are judged "untested", not "fixed".
- Casebook v1 headline: vetoes are the largest family (98/312, 31.4%,
  incl. 55 vetoes of S3 breakout-chases); limit orders are the largest
  entry family (81/154 entries, 52.6%); S1+S2+S3 cover only 47/312
  decisions (15.1%) — a coverage ceiling ahead of the hit-rate problem.

Paper trading only. Not investment advice.
