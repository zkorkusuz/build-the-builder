# Ten insights for other teams

From the Build the Builder hackathon, 10 and 11 October 2026. Each insight gives the evidence behind it and the
limit of the claim. Sources are result files under `results/`, reviews under `results/review-*.md`, traces under
`traces/`, commits by hash, and `docs/qa-review-sun.md`. Times are Istanbul.

## 1. Consistency beats peak

Claim. When a customer counts only if all three runs pass, a small per-run gap becomes a large score gap.
An agent right 90% of the time passes 73% of customers; 80% passes 51% (`PLAYBOOK.md` 7.4).

Evidence. Run 4 was right on 18, 19 and 20 of 21 customers in its three repetitions and passed 17 under three of
three (`results/run4-reps3.json`). Nine hours later run 20 was 21, 21, 21 (`run20-reps3.json`).

Limit. The cube assumes the three runs fail independently. In practice the same customer tends to fail twice,
which is worse for the score than the arithmetic suggests and is exactly what a rule gap looks like.

## 2. Ask of every failure: which decision did the model make that code could have made?

Claim. Treating each failure as a misplaced decision gives a fix that holds across runs; treating it as a
prompt problem does not.

Evidence. Sixteen decisions moved out of the model between Saturday 23:50 and Sunday 11:14
(`docs/figures/fig4-decisions.svg`): 4 to code steps, 7 to hooks, 2 to routes, 2 to fixed structure. The main
series went from 17 of 21 to 21 of 21 three of three in that window (`run4-reps3.json`, `run13-reps3.json`), and the
Northwind variant went from 11 of 13 to 13 of 13 three of three when the refusal count moved from the extractor to a
code step (`review-v1-variant.md`; `results/log.jsonl` at 03:23 and 03:45; commit b65c97f).

Limit. It works where the brief gives a rule to compute. Consent before a write, hardship wording and what
counts as a confirmation stayed with the model (`qa-review-sun.md`, rules 15, 32, 34).

## 3. Canonicalize in code, never in the model

Claim. Dates, day words and split answers must be turned into the form the API needs by code that sees the
call's reference date, not by the dialogue model.

Evidence. The model computed "next Friday" as a Saturday (EXT-16 in run 12, fixed by ca67b92), sent "14 March"
as "0003-03-14" and then joined it as "1988-03-03" (run 19, fixed by 89701fb), and read "Monday 2" as next Monday
instead of 2 November (run 26, fixed by c956bbf). Each fix is a unit test in `tests/test_dates.py` plus a clean
targeted rerun (`run21-targeted.json`, `run31-targeted.json`).

Limit. The parser is a list of shapes. "The twenty-second" was unparsed until Sunday 16:03 (5f24cee), amounts in
words are still not canonicalized (`qa-review-sun.md` B.12), and the hidden set will contain shapes nobody wrote.

## 4. Counters and caps belong in structure, not in prompts

Claim. "Ask at most twice" and "one persuasion attempt" are followed reliably only when a step count, a code
counter or a route enforces them.

Evidence. The opening became a fixed first ask plus one more step with a turn cap (e5e7b37); refusals are counted
in a code step from a single-turn classification (b65c97f); the callback window is checked and counted in a hook
(2468281). The judge still flagged "asked a third time" once when the count was the model's (EXT-05 in
`review-run24-reps3.md`).

Limit. A cap in structure still depends on the extractor classifying the reply. A hardship customer's "no" can be
counted as a refusal, which is why a special end reason now outranks the count (5e9b687, `qa-review-sun.md` B.4).
Tightening the extractor is not free either: raising the who-extraction confidence from 0.6 to 0.8 to stop a cut-off
line counting as a confirmation was reverted within ten minutes, because the asks_back run showed a clear yes the
extractor had missed outright, and a higher bar would turn such misses into a second ask that a questioning customer
fails (a957516, 0968f39, `review-run38-asks_back.md`).

## 5. Negative result: restating the policy each turn does not help, and prompt-only fixes did not move results

Claim. Reminding the model of the rules on every turn is not a fix. What helped was restating the state: an
instruction built from variables, such as "ask only for the year".

Evidence. Three prompt-only changes did not change behaviour. A prompt sentence telling the model to ask for the
rest of a split answer before calling the tool made the pieces style worse, 18 of 21, because the hook that joins
parts never ran (`review-run17-pieces.md`, fixed by sending partial answers to the tool, 404fc58). The sentence
"never fill in a part the customer did not say" (deea9f4) did not stop the model completing "the 21st of July,"
with an earlier year in a chat probe and in run 33 (`review-run33-reps3.md`). Mild hook text was ignored until the
hook blocked the call outright (404fc58). Two papers report the same: re-injecting goal text each turn did not
preserve the goal, and a naive running summary gained 1.1 points where an imperative restatement of state gained
about 20 (`docs/research-edge.md`, sections 1.1, 2.4 and 3.2).

Limit. There was no controlled A/B of per-turn policy re-injection on this agent. The evidence is three
prompt-only changes that did not move results, plus the literature. The agent's `what_to_do_next` lines are state
restatements, and those did move results.

## 6. Negative result: judge variance of about 3% and sandbox faults of about 1% are a floor

Claim. A share of lost calls has nothing to do with the agent, and no code change recovers them.

Evidence. In run 24, two of 63 calls failed on the judge alone with identical ledgers: the opening question was
counted as a persuasion offer and a name confirmation as an identity ask (`review-run24-reps3.md`). A judge failed
NW-13 because "This call may be recorded" preceded the promise (`review-v1-variant.md`). A sandbox fault, where every
hook and code step in one call fails, hit 1 of 105 calls across runs 19, 22 and 23 and 1 of 63 in run 26
(`review-run22-pieces.md`, `review-run26-pieces-x3.md`). Some verdicts come back "inconclusive" with the reason
"all criteria met" (`qa-review-sun.md` D.7).

Limit. Each rate rests on 60 to 105 calls, so the intervals are wide. The organizers' judge and scorer may treat
these cases differently from the local runner, which counts anything but "pass" as a fail.

## 7. Treat the platform as a flaky dependency, and learn its mechanics

Claim. Retries, timeouts and cancellation belong in one wrapper, and some platform behaviours decide the ledger.

Evidence. Two outages on Sunday afternoon, 13:59 to 14:20 and 14:23 to 14:59, each became a wrapper change: saves
retried inside the time budget (de0a864, a59f74b), the export written from the saved workflow (8e0662f), polls that
outlive a gap (da9b23a, 318dac2), orphan simulations cancelled (e7fe566). A mechanic that mattered: an emptied
request body is sent as null, the bank answers 400, the platform raises a function-call error and skips the
post-hook, so the agent said "technical issue" and the customer was lost (EXT-07 in `review-run22-pieces.md`). Hooks
now block a call by sending an invalid body, so the bank records nothing and the post-hook still runs (404fc58).
Run 37 took 2290 s against 428 to 909 s in the morning because of platform latency (`run37-reps3.json`).

Limit. The mechanics are Freya-specific. What transfers is the shape: one place for retries, never kill a runner
whose simulation is still running, and a triage rule for latency (median slowest turn above 10 s) before any fix.

## 8. Nothing from the brief in code, and field names from the API file

Claim. A builder must take every value, name and sentence from the brief and every field name from the API file,
and this needs a check, not a habit.

Evidence. The QA review at 13:30 found the request and response field names hard-coded in the hooks and a
`close_call` lookup that would crash on a path prefix or a `$ref` schema (`qa-review-sun.md` E.1 to E.3). The fix
reads names from the policy's field map, the role name or a keyword match, resolves paths by suffix and
dereferences schemas, with a unit test on a renamed API (de0a864, a59f74b). The attempt-2 rule, which was Brief A's
own, now comes from the policy (5f24cee). A test renders an empty policy and asserts no brief value appears
(`tests/test_render.py`, `test_no_brief_values_in_an_empty_policy_render`).

Limit. The policy schema still only holds shapes the team imagined: a deadline as the nth business day, a callback
window of today or the next business day (`qa-review-sun.md` B.9). A hidden brief outside those shapes is forced
into them.

## 9. Write expectations from the brief before any run, and test beyond the public set

Claim. Expectations written after seeing the agent drift toward the agent; the public set is too small to find
the rule branches the hidden set uses.

Evidence. The paper's builder that passed all 10 of its own tests scored 59.7% because its tests never reached
the hidden branches (`docs/sources.md`). This team's 21 cases are 3 public plus 18 written from the brief
(`tests/extra-cases.json`); they were run on two other calendar days (`run28-fri.json`, `run29-holeve.json`), in
all five speaking styles (`run14-in_words.json`, `run26-pieces-x3.json`, `run27-corrects-x3.json`,
`run38-talkative.json`, `run38-asks_back.json`), on a second bank built from an email, a memo and a code list
(`results/v1-variant.json`), and on Brief B against our own mock (`results/b-variant.json`, 10/17, five of the
seven losses hang-ups on slow turns).
The one expectation changed all day was wrong against the brief, not against the agent (5348e58).

Limit. Still 21 customers. The late-band two-refusal path, the day-month hint and a changed promise after recording
have no platform run on the final code; the multi-product rules have one mock run, which found two gaps in the
model's share of them (`qa-review-sun.md` B.3, B.10; `review-b-variant.md`).

## 10. Read the decision trail, not the score

Claim. A score says that a customer failed. Only the trail, with the maker of each decision, says whether the
cause is a rule gap, the model, the judge or the platform, and each needs a different response.

Evidence. Run 37's four failed calls all show the model's last turn taking 45 to 53 s and the customer hanging up,
with the ledger logic right in every completed call; the response was no code change (`review-run37-reps3.md`).
Run 24's two failures show identical trails passing in other repetitions; the response was a note, not a fix
(`review-run24-reps3.md`). The talkative run reads as a disaster at 7 of 21 until the trail shows 8 calls with no
customer turn and 6 personas cut mid-sentence; the response was again no fix (`review-run38-talkative.md`). Run 12's single failure showed the model computing a date; the response was a code step
(`results/run12-reps3.json`, EXT-16; fix ca67b92).

Limit. The triage is by hand with rules of thumb. A platform fault misread as a model decision wastes a fix; a
model decision misread as a platform fault hides a bug.
