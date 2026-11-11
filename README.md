# Brooks ES Paper-Trading Replication

## What this repository is

This is a **paper-trading research repository**. It documents an attempt
to learn Al Brooks' E-mini (ES) price-action system well enough to
replicate his intraday decisions with a small, explicit rule engine —
and to score that replication honestly against ground truth recovered
from the free public Brooks Trading Course daily review videos.

It is not a trading product, not a signal service, and not investment
advice. No real money is involved anywhere in this project: every trade
mentioned is a simulated replay on 5-minute RTH bars, settled on a
paper ledger of $10,000 trading MES micros ($5/point, max risk
$200/trade).

The workflow the repo records:

1. Recover dense, bar-anchored ground truth from the public review
   videos' narration (far denser than the written summaries).
2. Grade the engine's decisions against that truth, family by family
   (mentor grading / error book).
3. Only setup families that survive held-out validation may enter the
   tradable list. Everything else stays observe-only.

## Layout

- `engines/` — the rule engines, all original code from this project
  - `backtest-prev5-intraday-engine.py` — early backtest harness
  - `brooks-intraday-engine-v2.py` — v2 engine, frozen for Period 1
  - `brooks-intraday-engine-v3.py` — v3 engine, frozen 2026-11-04 for
    Period 2 (adds an S2 depth gate, an S2 structural stop, and a
    late-session weak-S3 gate). Frozen engines are never edited after
    the fact — a rule change means a new version.
- `data/casebook-v1.json` — casebook v1: 312 bar-anchored decision
  points from 6 days, classified by setup family. Classification only
  (date / bar / family / direction / oral timestamp). No transcript
  text.
- `docs/` — the research record, in order:
  - `brooks-replication-v2-2026-10-16-22.md` — v2 replication report
  - `brooks-1020-oral-vs-text-measured-2026-10-28.md` — why oral truth
    matters: oral narration carries ~60 decision points/day vs ~5 in
    the written version
  - `brooks-v3-rules-and-period2-2026-11-04.md` — v3 rules + Period 2
    setup
  - `brooks-casebook-v1-2026-11-10.md` — casebook v1 report
  - `brooks-s3-grading-and-spec-notes-2026-11-11.md` — mentor grading
    of the two Period-2 S3 trades + draft S3 encoding spec (15 rules)
  - `brooks-s1-exit-grading-2026-11-11.md` — mentor grading of the
    three Period-2 S1 trades + exit-management inventory (53 points)
  - `brooks-learning-todo-plan-2026-11-10.md` — the 5-stage learning
    plan this project follows

## Results so far (2026-11-11)

- Period 1 (v2): $10,000 → $9,719.00 (−$281.00). Verdict: not worth
  encoding as-is; the S2 failed-breakout family went 0/3.
- Period 2 (v3, 5 US sessions 11-04–11-10): 5 trades, 2 wins,
  $10,000 → $10,116.75 (+$116.75). S3 2/2 (+$277.25), S1 0/3
  (−$160.50), S2: 0 trades — its depth gate / structural stop are
  judged "untested", not "fixed". Owner verdict: worth encoding,
  S3-led; S1/S2 decided separately.
- Mentor grading then cooled the headline: the two S3 trades grade as
  "1 family hit + 1 direction hit with self-invented timing", not
  "S3 verified". The three S1 losses were all rule problems (entries
  released by flickering/lagging day-type labels on what ended as
  range days), not execution problems. The engine's veto/abstention
  quality is currently its most solid evidence.
- Casebook v1 headline: vetoes are the largest family (98/312, 31.4%,
  incl. 55 vetoes of S3 breakout-chases); limit orders are the largest
  entry family (81/154 entries, 52.6%); S1+S2+S3 cover only 47/312
  decisions (15.1%) — a coverage ceiling ahead of the hit-rate problem.

## How this repo is kept current

New knowledge is pushed here as it is produced: grading reports, spec
drafts and plan updates land in `docs/` in the same working session
that produced them. Engine code changes only when a spec has been
frozen and passed held-out validation, and always as a new version —
frozen engines stay frozen.

## What is deliberately NOT in here

- Brooks video transcripts (text or PDF) — the narrator's spoken words
  are course content; not republished. Analysis snippets quoted in the
  reports are a few words at most.
- Ground-truth JSONs — they carry short verbatim quotes item by item;
  each needs a de-sensitisation pass before any of it can go public.
- Engine decision/trade logs and portfolio ledgers — internal working
  files; add later only if the owner wants them public.

Paper trading only. Not investment advice.
