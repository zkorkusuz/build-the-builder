# Methodology

How the builder was built and tested on 10 and 11 October 2026. Times are Istanbul. Sources are result files
under `results/`, traces under `traces/`, commits by hash, and `docs/qa-review-sun.md`.

## 1. The design principle

A hidden customer counts only when the ledger is exact and the judge finds nothing, in all three runs. The cube
of the per-run rate decides everything: an agent right 95% of the time passes 86% of customers, 90% passes 73%,
80% passes 51% (`PLAYBOOK.md` 7.4). So the target was not a better average answer but fewer decisions that come
out differently from run to run.

The working rule: a failure is a decision the model made that code could make instead. For every failed call the
review loop prints the decision trail with the maker of each step (code, hook, route, extraction, model) and asks
which model decision could be moved. Sixteen were moved between Saturday 23:50 and Sunday 11:14: counting asks and
refusals, converting dates, joining split answers, checking the callback window, naming the end reason, the
outcome and the close (`docs/figures/fig4-decisions.svg`). Where they went: 4 code steps, 7 hooks, 2 routes, 2
pieces of fixed structure, and 1 prompt sentence for the one decision only the model can make. The model speaks in
5 of the agent's 40 steps.

## 2. The pipeline

One command: `builder/build.py <brief files> <openapi.json>`. The builder works in its own folder holding only its
skill, the brief files and the API file, so no practice value can leak into a hidden build. Measured over the 20
complete Brief A builds in `traces/brief-a-20261011-*.log`:

| Stage | What it does | Time | Claude cost |
|---|---|---|---|
| normalize | one Claude Opus call reads every brief line into `policy.json` in a fixed schema and lists each ambiguity it resolved; a section of the wrong type is emptied and sent back for repair (c2a7d94) | 64 to 85 s | $0.22 to $0.43 |
| render | Python fills a fixed template; dates, floors, counters and guards become code steps and hooks, the flow becomes routes, the brief's sentences become fixed lines; field names come from the API file (de0a864) | under 1 s | 0 |
| adapt | one Claude call checks the prompts rule by rule and adds text only for what structure cannot carry | 9 to 16 s | $0.14 to $0.16 |
| lint and dry run, save and publish in one slot per brief set, export, trace | | seconds | 0 |
| whole build | | 87 to 107 s | $0.36 to $0.58 |

A build stops itself inside 30 minutes and always ends with a saved workflow. The trace holds start and end,
every model call with its purpose, seconds and cost, the workflow and agent ids, step and tool counts, every
rule's home, every ambiguity and the mapped field names; the policy that produced the agent is saved next to it
(43cf46e).

## 3. The test layers

1. Unit tests: 53 (`tests/test_dates.py` 28, `test_render.py` 18, `test_normalize.py` 7). They execute the hook
   and code-step source strings from a rendered workflow, the date engine and the normalize checks.
2. Lint and dry run on every build: the trace line `render: 40 steps, 36 tools, lint clean`; a failed dry run is
   traced and does not end the build (de0a864).
3. Chat probes with `tools/chat.py`: one digit per turn, a date in two parts, the truncated-answer path (session
   notes of 08:41 and 11:20; probes are not stored in the repository).
4. The 21-case regression three of three: 3 public cases plus 18 written from the brief for what the public set
   misses (`tests/extra-cases.json`). Results: 17/21 (`run4-reps3.json`), then 21/21 on `run13`, `run20`, `run23`,
   `run25`, `run32`; 19/21 on `run24` and 20/21 on `run33`, both misses judge variance or a persona artifact.
5. Five speaking styles: in_words 21/21 (`run14-in_words.json`); pieces 16, 18, 19, 20 of 21 by version, then 19/21
   three of three (`run26-pieces-x3.json`) with the two misses fixed and rerun clean (`run31-targeted.json`);
   corrects 21/21 three of three (`run27-corrects-x3.json`); asks_back 18/21 (`run38-asks_back.json`: a persona that
   never spoke, a judge reading of the ask-once rule, a missed confirmation); talkative 7/21
   (`run38-talkative.json`): all 14 losses on the simulator side, 8 calls with no customer turn and 6 with lines cut
   mid-sentence, so no agent rule gap (`review-run38-talkative.md`).
6. Other calendar days with `tests/day_cases.py`: Friday 16 October 21/21 (`run28-fri.json`); holiday eve 23 October
   18/19 (`run29-holeve.json`), the miss a simulator persona cutting its line short.
7. Two variant banks: Northwind from an email, a memo and a code list, run against our own mock bank through a
   tunnel (`tests/variant_run.py`, `tests/mock_bank.py`); 13/13, then 11/13 three of three when the refusal count
   lived in the extractor, 13/13 three of three once it was a code step, 13/13 on the final code
   (`results/v1-variant.json`, `review-v1-variant.md`). Harbor Credit Union, a clean spec with three identity
   questions, a six-day week, three attempts and no floor, through normalize, render, lint and dry run (5f24cee);
   not simulated. Brief B, built from both practice briefs and run on the same mock with 17 cases: 10/17
   (`results/b-variant.json`, `review-b-variant.md`); 5 losses were hang-ups on 32 to 73 s agent turns, 2 were
   multi-product rule gaps fixed for that path only (a7ecb70), rerun queued as run 39.
8. A renamed tool API: paths with a prefix, `$ref` schemas, renamed request and response fields, covered by
   `test_renamed_api_fields_and_ref_schemas` (de0a864, a59f74b). A normalize check on a renamed API file filled
   the field map exactly (session note of 14:10; the file is in a session scratchpad, not the repository).

Across the day the result files hold about 1,400 scored calls.

## 4. The review loop

`tools/review_run.py <results file>` prints, for every failed call, the ledger difference, the judge's reason, the
final variables and the decision trail with each step's maker (5341f72). The fix for a rule gap is a unit test, a
code change, a targeted rerun with `--only` three times, then the full set three times. A reviewer agent reads
every change before it is committed (025a189, 4565211, 1aca823, a59f74b, 9739b08). An independent QA review at
13:30 mapped all 47 Brief A rules to their homes, ranked 12 gaps and scripted 30 edge cases
(`docs/qa-review-sun.md`); eight of its ten actions were done by 16:03.

Expectations are written from the brief before any run and never changed to make the agent pass. The one
expectation changed all day was wrong against the brief: the third-party "tomorrow" case on a day when tomorrow is
not a business day (5348e58).

## 5. Keeping platform losses out of the agent's score

Five kinds of loss are not agent errors and are logged, not fixed:

- Model latency. The runner prints the median slowest agent turn per repetition. Above 10 s the platform's model
  was busy and customers hang up on the silence (`README.md`). Run 37 at 16:08 was 21, 19, 19 of 21 with medians of
  12 to 15 s against 2 to 4 s in the morning; all four failed calls were customer hang-ups during turns of 45 to
  53 s, and the ledger logic was right in every completed call (`run37-reps3.json`, `review-run37-reps3.md`).
- Outage. A repetition where no customer has a tool call and the agent turn is 0 s never ran; the runner discards
  it once and repeats it after five minutes (e7fe566).
- Sandbox fault. Every hook and code step in one call fails with "Sandbox did not return a parseable result";
  the trail shows the model calling the tool with the right body and the bank answering an error (EXT-07 in
  `review-run22-pieces.md`, EXT-12 in `review-run26-pieces-x3.md`). Seen in 1 of 105 calls across runs 19, 22 and
  23 and in 1 of 63 in run 26: about 1%.
- Judge variance. The same transcript passes in two repetitions and fails in the third with a reason that
  misreads a rule: the opening question counted as a persuasion offer, a name confirmation counted as an identity
  ask (`review-run24-reps3.md`, 2 of 63 calls, about 3%); "This call may be recorded" counted as "recorded" before
  a promise (NW-13 in `review-v1-variant.md`). Locally, an "inconclusive" verdict counts as a fail.
- Simulator persona faults. The customer never speaks, or its line is cut mid-sentence so the digits or the year
  never arrive. Rare in the plain styles (PUB-03 twice in about nine runs), dominant in talkative: 14 of 21 calls
  in `run38-talkative.json`, read one by one in `review-run38-talkative.md`. A simulator persona that never speaks
  looks like an agent that went silent; the slowest-turn column at 0.0 s tells them apart.

## 6. The two outages of Sunday afternoon

First, 13:59 to 14:20. Platform reads and writes timed out or returned 504. A Brief B build sat in save retries
for 17 minutes and saved at 14:20 (`traces/brief-a_brief-b-20261011-140159.log`). What the tooling learned: the
save is retried only while more than ten minutes of the budget remain, a 4xx falls back to the bare template so a
workflow always exists (de0a864, a59f74b), the export is written from the workflow as saved when the platform does
not answer the read (8e0662f), and a failed variant build prints its stderr.

Second, 14:23 to 14:59. The Brief B run's first status poll got three 504s in a row, the runner died and its
simulation was orphaned, pointing at a dead tunnel. What the tooling learned: status polls and iteration reads
wait through an outage, 120 tries of 20 s, and a cancelled simulation ends the wait (da9b23a); a 4xx on such a read
ends it at once, because a deleted simulation is an answer (318dac2); an orphan is cancelled with the wrapper's
cancel call rather than deleted by hand in the dashboard (e7fe566, used at 15:02); the chain restarts only after
two good watcher checks; and Brief A is never rebuilt while a simulation runs on its slot. A third Brief B attempt
at 15:06 crawled at 5 of 17 calls placed in 18 minutes and was deleted. The regression that followed, run 37, took
2290 s against 428 to 909 s in the morning.
