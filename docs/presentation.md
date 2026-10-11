# Build the Builder: six slides

Freya x YC hackathon, 10 to 11 October 2026. Times are Istanbul. Every claim names its source: a result file
under `results/`, a review under `results/review-*.md`, a trace under `traces/`, a commit hash, or a document
under `docs/`. Figures are in `docs/figures/`. Written at 16:30 on Sunday, before the hidden briefs opened.

Three numbers to say out loud:

- 21 of 21 practice customers passed in all three repetitions, on five separate full runs
  (`results/run13-reps3.json`, `run20-reps3.json`, `run23-reps3.json`, `run25-reps3.json`, `run32-reps3.json`).
- 16 decisions moved out of the model into code steps, hooks, routes and fixed structure in one day
  (`docs/figures/fig4-decisions.svg`).
- About 1% of calls lost to a platform sandbox fault and about 3% to judge variance. That is the floor no agent
  code removes (`results/review-run22-pieces.md`, `review-run26-pieces-x3.md`, `review-run24-reps3.md`).

---

## Slide 1. The score rewards consistency, not peak

Figure: none. One small table.

| Agent right, per run | Customers passing all three runs |
|---|---|
| 95% | 86% |
| 90% | 73% |
| 80% | 51% |

- 60 hidden customers across two briefs. A customer counts only when the bank's ledger is exact and a judge model
  finds no policy or honesty problem, in all three runs (`docs/sources.md` section 1; `PLAYBOOK.md` section 2).
- The table is the cube of the per-run rate (`PLAYBOOK.md` section 7.4; `docs/qa-review-sun.md`, scoring reminder).
- The organizers' background paper: the best coding-agent builder passed 23.9% of hidden conversations, 5.9% in
  banking; expert-built agents 82.2% (`docs/sources.md`, Table 2).

Speaker notes (69 words):
The score is customers passed in all three runs. Cubing is brutal: an agent right nine times in ten passes fewer
than three customers in four. The organizers' own paper shows why builders fail: the best one reached 24 percent,
and 6 in banking, where the rules are densest. So we did not chase a higher peak. We chased the decisions that
come out differently from run to run.

---

## Slide 2. The principle: a failure is a decision the model made that code could make instead

Figure 4: `fig4-decisions.svg`, a timeline of the 16 decisions, Saturday 23:50 to Sunday 11:14, each marked
with its new home.

- For every failed call the review loop prints the decision trail and asks one question: which decision did the
  model make that code, a hook or a route could have made instead? (`tools/review_run.py`, commit 5341f72;
  example trail in `results/review-run37-reps3.md`.)
- Where the 16 went: 4 to code steps, 7 to hooks, 2 to routes, 2 to fixed structure, 1 left to the model as a
  prompt sentence (figure 4 inset).
- Examples and their commits: counting the opening asks (e5e7b37), days said in words (ca67b92), joining split
  answers (4575681, 89701fb), naming the end reason on the transition (2468281), a close step on every exit path
  (35d2638).
- The model speaks in 5 of the agent's 40 steps; the rest are code, api_request and end_call steps
  (`fig1-architecture.svg`; trace line `render: 40 steps, 36 tools` in `traces/brief-a-20261011-160901.log`).

Speaker notes (79 words):
Every fix started from a transcript. The model computed 'next Friday' as a Saturday, so the date engine computes
it now. It joined '14 March' and '1988' as the third of March, so the hook joins parts now. It counted asks
loosely, so the opening is a fixed chain of steps. Fifteen of sixteen decisions left the model. The last one,
never fill in a year the customer did not say, stays a prompt sentence and still fails sometimes.

---

## Slide 3. The pipeline: one command, about 100 seconds, about half a dollar

Figure 1: `fig1-architecture.svg`, the rendered Brief A agent: 40 steps in six phase bands, hooks marked.

Timings and costs are the range over the day's Brief A traces (`traces/brief-a-20261011-*.log`, 20 complete builds):

| Stage | What it does | Time | Claude cost |
|---|---|---|---|
| normalize | one Claude Opus call reads every brief line into `policy.json` and lists each ambiguity it resolved | 64 to 85 s | $0.22 to $0.43 |
| render | Python fills a fixed template: dates, counters and guards in code steps and hooks, the flow in routes | under 1 s | 0 |
| adapt | one Claude call adds prompt text only for rules the structure cannot carry | 9 to 16 s | $0.14 to $0.16 |
| lint, dry run, save and publish, export, trace | | a few seconds | 0 |
| whole build | | 87 to 107 s | $0.36 to $0.58 |

- The builder runs in its own folder with only its skill, the brief files and the API file (`README.md`, builder
  section). It stops itself inside 30 minutes and always leaves a saved workflow.
- The trace carries every model call with its cost, every rule's home, every resolved ambiguity and the tool field
  names mapped from the API file (`traces/brief-a-20261011-160901.log`).

Speaker notes (76 words):
Two model calls, fixed code between them. Normalize reads the brief into a policy file and writes down every
ambiguity it resolved. Render is plain Python: it puts dates, counters and guards into code steps and hooks, and
the call flow into routes. Adapt adds prompt text only where structure cannot carry a rule. Lint, a dry run,
publish, export, trace. A brief becomes a published agent in about a hundred seconds for about fifty cents.

---

## Slide 4. Evidence

Figure 2: `fig2-results.svg`, customers passed in all 3 of 3 by agent version. Figure 3: `fig3-robustness.svg`,
styles, other days, a variant bank. Use figure 2 on the slide and figure 3 as the backup slide if time is short.

- Main series: 17 of 21 at Saturday 23:35 (`results/run4-reps3.json`), 21 of 21 three of three at 01:57
  (`run13-reps3.json`), and 21 of 21 again at 08:45, 09:20, 10:00 and 10:45 (`run20`, `run23`, `run25`, `run32`).
  The misses in runs 24 and 33 were judge variance on identical ledgers and a persona that cut its own sentence
  short (`review-run24-reps3.md`, `review-run33-reps3.md`).
- Speaking styles: in_words 21/21 (`run14-in_words.json`); corrects 21/21 three of three (`run27-corrects-x3.json`);
  pieces 19/21 three of three with one sandbox fault and one parser bug, fixed in v48 and rerun clean
  (`run26-pieces-x3.json`, `run31-targeted.json`). Talkative and asks_back were queued as run 38 when this was
  written and are not in the repository yet.
- Other calendar days: Friday 16 October 21/21 (`run28-fri.json`); holiday eve 23 October 18/19, the miss a
  simulator persona truncating its own line (`run29-holeve.json`, `review-run29-holeve.md`).
- Two other banks: Northwind, built from an email, a memo and a code list, 13/13 on the final code
  (`results/v1-variant.json`, 10:26); Harbor Credit Union, a clean spec with three identity questions, a six-day
  week and no floor, through normalize, render, lint and dry run only (commit 5f24cee). Not simulated.
- A renamed tool API with `$ref` schemas: unit test `test_renamed_api_fields_and_ref_schemas` (commit de0a864).
- Final full run on v54, 16:08: 18/21. All four failed calls were customer hang-ups during agent turns of 45 to
  53 s while the median slowest turn was 12 to 15 s against 2 to 4 s earlier in the day; no code change
  (`run37-reps3.json`, `review-run37-reps3.md`).

Speaker notes (80 words):
The line is customers passing all three repetitions: four short on Saturday night, all twenty-one by two in the
morning, and all twenty-one again on four later runs. The amber points are not agent errors: a judge that read
the opening as an offer, a persona that cut its sentence short. Figure 3 is the same agent on other calendar
days, on customers who split numbers or correct themselves, and on a bank built from an email and a memo.

---

## Slide 5. Errors, both kinds

Figure: none. The hook badges in figure 1 show where the conversation guards live.

In the conversation, a hook before and after every tool call:

- A blocked call never reaches the bank: the hook replaces every value with an invalid one, so the bank records
  nothing and the post-hook still runs and tells the model what to say (commit 404fc58).
- "Recorded" is spoken only after the bank answers ok; the post-hook writes the sentence (`docs/qa-review-sun.md`
  section D.1).
- One promise per product: a second `create_promise` for a recorded product is blocked (commit 5e9b687).
- A bank rejection is corrected at most twice, then the service-error path (commit 1aca823).
- A failed service is never claimed: two failures close as no_promise with reason service_error
  (`qa-review-sun.md`, rule 37).

On the platform:

- Retries live in one place, the Freya wrapper: twice on a 5xx or a dropped connection (89b0409, b53721e).
- The build's save is retried until ten minutes before the 30-minute cap; a 4xx falls back to the bare template
  (de0a864, a59f74b). One build saved after 17 minutes of retries during the first outage
  (`traces/brief-a_brief-b-20261011-140159.log`, 1478 s).
- The export is written from the workflow as saved when the platform does not answer the read (8e0662f).
- Status polls outlive an outage, 120 tries of 20 s; a cancelled or deleted simulation ends the wait (da9b23a, 318dac2).
- A stuck simulation can be cancelled (e7fe566). A watcher logged the platform every two minutes; it lives in the
  session's scratchpad, not in the repository.
- The runner discards a repetition the platform never ran and repeats it after five minutes (e7fe566). The review
  loop tags every decision with its maker, so a platform loss is logged and never "fixed" in the agent
  (`review-run37-reps3.md`).

Speaker notes (80 words):
Two kinds of error, two defences. Every tool call has a hook before and after it. A blocked call never reaches
the bank. The word recorded is spoken only after the bank said ok. The platform went away twice, for twenty-one
and for thirty-six minutes. Each outage became a wrapper change: saves retry inside the budget, the export is
written from what was saved, polls outlive a gap, orphans get cancelled. Platform losses are logged, not fixed in
the agent.

---

## Slide 6. Method and limits

Figure: none.

Method:

- Expectations were written from the brief before any run and never changed to match the agent (`PLAYBOOK.md`
  section 7.2; `tests/extra-cases.json`; `tests/day_cases.py`). One expectation was corrected because it
  contradicted the brief, not the agent: the third-party "tomorrow" case on a day when tomorrow is not a business
  day (commit 5348e58).
- The review loop prints every decision with its maker (`tools/review_run.py`; every `results/review-*.md`).
- A reviewer pass after every change (commits 025a189, 4565211, 1aca823, a59f74b, 9739b08).
- An independent QA review at 13:30 (`docs/qa-review-sun.md`): all 47 Brief A rules mapped to their homes, 12 gaps
  ranked, 30 scripted edge cases, 10 actions. Eight actions have a commit (5e9b687, 1aca823, de0a864, a59f74b,
  5f24cee, 70ee3fc). Action 6, Brief B on our own mock, was running when this was written; the third-party turn
  cap in action 9 stayed at 6.
- Eighteen papers read for what transfers (`docs/research-edge.md`, commit c84f81c); the identical-promise guard
  came out of it (8f09f05).

Limits (`docs/qa-review-sun.md` unless stated):

- Multi-product negotiation is prompt-only; the deterministic routes need one product (section A, Brief B table).
- The second persuasion attempt's wording comes from the policy since 5f24cee, but its logic is still the
  floor-or-full choice.
- Consent before a write is a model judgement, not an extracted yes (rule 34).
- A customer hang-up leaves the ledger without `close_call` (C.10).
- Judge variance about 3% and sandbox faults about 1% are a floor (`review-run24-reps3.md`, `review-run26-pieces-x3.md`).

Speaker notes (79 words):
Three habits made the day. Expectations were written from the brief before the agent ran, and never bent to fit
it. Every failure was read as a decision trail with its maker named: code, hook, route, extraction, or model. A
reviewer checked every change, and an independent review at half past one mapped all forty-seven rules to their
homes. The limits: multi-product negotiation is still prompt-only, consent is still the model's call, and a
hang-up leaves the ledger open.

---

Close on the three numbers: 21 of 21 three of three; 16 decisions moved out of the model; about 1% sandbox and
3% judge noise as the floor.
