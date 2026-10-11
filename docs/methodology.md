# Methodology

## 1. The principle
A collections call has rules that a bank writes down: when to ask, what to say, which date, which amount, which outcome
code. A language model can follow most of them most of the time. The hackathon scores a customer only when all three
runs pass, so "most of the time" is the problem. The design rule used all weekend: when a call fails, find the one
decision the model made that code could have made instead, and move it. Dates, counters, joins of split answers,
the outcome code, the close, the read-back values: all computed in code steps or hooks that run in milliseconds and
give the same answer every time. Routes carry the flow on extracted choices. Fixed lines carry the brief's
verbatim sentences. The model speaks, and judges only what no structure can decide (hardship, dispute, a scam
question). Sixteen such moves are listed in `docs/figures/README.md` and drawn in figure 4.

## 2. The pipeline
One command: `.venv/bin/python builder/build.py <brief files...> <openapi.json>`. Stages, with the Brief A timings
from `traces/brief-a-20261011-170440.log`:

| Stage | Who | What | Time, cost |
|---|---|---|---|
| Normalize | Claude Opus, one call | Reads every brief file in full and the API file into `policy.json` in a fixed schema: calendar, bands, identity questions, outcomes, end reasons, transfers, sentences, rules verbatim, ambiguities, the API's field names by role | 60 to 80 s, about $0.25 |
| Render | Python | A 40-step workflow from the policy: code steps for facts and outcomes, hooks around every tool call, routes on extractions, fixed lines | under 1 s |
| Adapt | Claude Opus, one call | Rule-by-rule check of the prompts; adds text only for what the structure does not carry | 11 to 16 s, about $0.15 |
| Lint, dry run | Python, Freya | The silent platform gotchas; the platform's own validation | seconds |
| Save, publish, export | Freya | One slot per brief set, updated in place; export to `<slot>.workflow.json`; the policy saved next to the trace | seconds |

About 95 seconds end to end on a healthy platform; 1478 seconds once, when the platform hung for 17 minutes and the
save loop kept trying (`traces/brief-a_brief-b-20261011-140159.log`). The builder runs in its own working folder
with only the briefs and the API file; nothing from a practice brief is in the code, which `tests/test_render.py`
checks by rendering an empty policy and grepping for Brief A values.

## 3. Test layers
| Layer | What it checks | Cost |
|---|---|---|
| 53 unit tests | Date engine, hooks executed as rendered, policy schema, a renamed tool API, the empty-policy render | 0.2 s |
| Lint and dry run | Platform gotchas; Freya's validation | at build time |
| Chat probes | One scripted path, turn by turn, to see one decision and the variable table | a minute |
| Regression set | 21 Brief A customers: 3 public plus 18 extra written from the brief before any run; three repetitions; a customer passes only if all three pass | 10 to 35 minutes |
| Speaking styles | Numbers in words, in pieces, self-corrections, talkative, asks back | 5 to 12 minutes each |
| Other days | Friday, holiday eve, with recomputed expectations | 5 minutes each |
| Other banks | Northwind (email, memo, code list, other questions and outcome names) and Harbor (three identity questions, Saturday business days, one band with three attempts, no floor, renamed fields and enums), each against our own mock bank behind a tunnel or through the dry run | 15 minutes |
| Public cases without answers | The ten practice customers whose security answers the kit does not carry, run against our own mock with answers we define | 15 minutes |

Expectations are written from the brief first and never changed to match the agent. When an expectation was wrong,
the test was corrected from the brief and said so in the log (tracker run 15).

## 4. The review loop
`tools/review_run.py results/<run>.json` prints, for every failed call, the ledger mismatch or the judge's reason and
then the decision trail from the call's own events: each step entered with the engine's reason, each tool call with
the arguments the model chose, each hook instruction, each line said, every decision tagged with its maker. Across
repetitions it marks a case as flaky (a model judgement) or always failing (a rule gap). The question asked of each
failure is the principle in section 1. After a fix: the failed cases three times with `--only`, then the full set
three times. A reviewer agent reads every change against the hard rules before it is committed; twice on Sunday it
found a blocker the tests had not.

## 5. Keeping the platform's noise out of the agent's score
Measured on Sunday and written in the tracker:
- Sandbox fault: about one call in a hundred gets "Sandbox did not return a parseable result" with a correct hook body inside, and every later hook in that call fails. Nothing in a workflow runs without the sandbox. The close tool now carries two platform retries because a fault on the close has no model turn left to retry it (6bac784).
- Judge variance: about three calls in a hundred get a wrong verdict on an identical transcript (the opening question counted as an offer; the name confirmation counted as a security ask). "Inconclusive" means the analysis never ran.
- Latency hang-ups: when the platform's model is slow (median slowest turn 12 to 15 s against 2 to 4 s), the simulated customer hangs up on the silence; the ledger logic was right in every such call (results/review-run37-reps3.md).
- Persona artifacts: the simulated customer sometimes cuts its own line short; the talkative style lost 14 of 21 calls to this and to calls dying after the first reply (results/run38-talkative.json).
- Platform outages: two on Sunday afternoon. The first killed a build at its save; the second killed a runner on a status poll. Both are now survived by the wrapper and the build (commits 89b0409, 8e0662f, da9b23a, 318dac2), and a watcher raises an alert within six minutes.
The runner prints a slow-model warning and discards a repetition the platform never ran; the review loop reads the
call's end reason before anything is called an agent fault.

## 6. What is still the model's
Multi-product negotiation (per-product attempts, one read-back for all, the order of products) is prompt-driven:
4 to 5 of 10 on our mock, about half of the misses hang-ups. The opening's confirmation extraction can miss a plain
"yes" (one call in the asks-back run). The model retries a failed recording without telling the customer first. Each
is written down with its trail; none was changed after the freeze because none could be measured three times before
the hidden briefs.
