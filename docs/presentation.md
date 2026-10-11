# Build the Builder: six slides

Figures are in `docs/figures/`. Every number below names its source: a results file, a trace, or a commit.

## Slide 1. The game is pass-all-three
Figure: none, one table.

| | |
|---|---|
| Score | hidden customers passed in all 3 of 3 runs, out of 60 |
| 90% per run | 73% of customers |
| 80% per run | 51% of customers |
| Paper's best builder | 23.9%; banking 5.9%; expert ceiling 82.2% (τ^τ-bench, docs/sources.md) |

Notes (≤80 words): The scorer reads the bank's ledger, a judge reads the transcript, and a customer counts only if all three runs pass. So the target is not a good agent on average but an agent that makes the same decision every time. That ruled out one approach on Saturday night: a prompt with 47 rules and a model that counts, computes and remembers. Ninety-two percent of the paper's builders built exactly that.

## Slide 2. The principle: the model only speaks
Figure 4, `fig4-decisions.svg`.

Notes: Every failure in the review loop was traced to one decision the model had made that code could make instead, and the decision moved. Sixteen moves in one day: how many times to ask, what "next Friday" means, how to join "14 March" and "1988", when the attempts are used up, which outcome code to send, when to close. Seven went into hooks, four into code steps, two into routes, two into fixed lines, one stayed a prompt rule. After each move the case passed three of three (results/log.jsonl, tracker run log).

## Slide 3. The pipeline
Figure 1, `fig1-architecture.svg`.

Notes: Normalize: one model call reads every line of the brief and the tool API file into a policy in a fixed schema, ambiguities listed (traces/brief-a-20261011-170440.log). Render: Python fills a workflow from the policy; dates, counters, guards and the outcome live in code steps and hooks, the flow in routes. Adapt: one model call adds prompt text only for what structure cannot carry. Lint, dry run, publish, export, and the policy saved next to the trace. About 95 seconds and $0.50 per brief.

## Slide 4. Evidence
Figure 2, `fig2-results.svg`; Figure 3, `fig3-robustness.svg`.

Notes: From 17 of 21 three of three on Saturday night to 21 of 21 three of three by 02:00, then held through every change: versions 40, 42, 46, 48 all 21 of 21 three of three (results/run20, run23, run25, run32). Robustness: five speaking styles, two other calendar days, two other banks (Northwind 13 of 13 three of three; Harbor through the pipeline and the platform's dry run), a tool API with eight renamed fields and a prefixed path (tests/test_render.py). The frozen build: 21 of 21 (results/run41-v62.json).

## Slide 5. Errors, in the call and on the platform
Figure: none, two columns.

In the call: a blocked tool call sends values no bank accepts, so the bank records nothing and the hook speaks (commit 404fc58); "recorded" only after the bank says ok; one promise per product (5e9b687); a bank rejection corrected at most twice; a failed service never claimed; a bank answer "already exists" treated as recorded (1aca823).

On the platform: retries in one place; a save loop bounded by the budget with a bare-template fallback; the export written from the saved workflow if the read fails (8e0662f); polls that outlive an outage but stop on a 404 (da9b23a, 318dac2); a cancel for stuck simulations; a watcher that alerts within six minutes; a runner that discards a repetition the platform never ran.

Notes: Two outages on Sunday afternoon, 13:59 to 14:20 and 14:23 to 14:59, found every one of these holes before 20:00 (tracker log l59). The platform's own noise is the floor: about one call in a hundred fails in the sandbox, about three in a hundred get a wrong judge verdict, and when the platform's model is slow the simulated customer hangs up on the silence (results/run37-reps3.json: 4 calls, all customer-ended at 27 to 50 s turns).

## Slide 6. Method, and what is still the model's
Figure: none.

Notes: Expectations were written from the brief before any run and never changed to fit the agent. The review loop prints every decision in a failed call with its maker: code, hook, route, extraction or model (tools/review_run.py). A reviewer agent after every change found a blocker twice (hooks text with brief wording; a transfer hook without its field map). An independent QA review and eighteen papers read for what transfers (docs/qa-review-sun.md, docs/research-edge.md). Still the model's: multi-product negotiation (4 to 5 of 10 on our mock, half of it hang-ups), the opening's confirmation extraction, the silent retry after a failed recording.

## Three numbers
- 21 of 21, three of three, on the practice set at normal platform speed.
- 16 decisions moved out of the model in one day.
- About 1% sandbox and 3% judge noise: the floor no code removes.
