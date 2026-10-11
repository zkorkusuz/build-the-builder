# QA review of the builder and the generated Brief A agent

Sunday 11 October 2026, 13:30 Istanbul. Read-only review before the hidden briefs open at 20:00.

What was reviewed: PLAYBOOK.md, docs/sources.md, both practice briefs, tools/openapi.json, public-test-set.json, the 21 regression cases on three calendar days (results/cases-wed.json, cases-fri.json, cases-holeve.json), tests/extra-cases-b.json, the Northwind variant (tests/variants/v1), every file in builder/, the three unit-test files, the newest Brief A export (brief-a.workflow.json, agent 70e93e68, version 52, built 11:14 from work/brief-a/policy.json), the old Brief B export (brief-a_brief-b.workflow.json, 01:16), docs/research-edge.md, every results/review-run*.md, results/log.jsonl, the platform docs (workflow-format.md, tools-and-code.md), freya.py, tools/score.py and tools/run_cases.py.

What was verified locally (no platform calls): the 49 unit tests pass; the exported workflow is byte-identical to a fresh `render.render(work/brief-a/policy.json, tools/openapi.json)` except for the three adapt additions and platform-added default keys; and the specific claims marked "(verified)" below were checked by executing the hook and code-step source strings from the rendered workflow, or `builder/dates.py` functions, in a local Python process, the same way tests/test_render.py does.

Scoring reminder used throughout: a hidden customer counts only if the ledger is exact and the judge finds nothing, in 3 of 3 runs. A decision that the model gets right 95% of the time passes a customer 86% of the time.

---

## A. Rule coverage matrix

Homes: **fixed** = a fixed spoken line (`on_enter.text` or a terminal `spoken_message`); **code** = a code step; **hook** = a tool pre/post hook; **route** = a transition on a variable or an extracted enum; **prompt** = instruction text the dialogue model must follow; **extractor** = the extraction model's classification (a model decision, but not the dialogue model's). File references are to builder/ unless stated. Step names are those in brief-a.workflow.json.

### Brief A

| Rule | What it requires | Where it lives | Practice case | Note |
|---|---|---|---|---|
| 1 | Opening: digital assistant, call recorded; no "collections/debt/payment/product" before verification, relatives included | **fixed**: `opening.on_enter.text` from `policy.opening_sentence` (render.py `render`); forbidden words: **prompt** (prompts.py `system_prompt`) plus **structure**: debt facts only exist after step `account`, reachable only on `id_state == verified` | PUB-01, PUB-02, EXT-01/02/03/05 | The structural half is strong: before `account_facts` runs, `debt_summary` is "not loaded yet". |
| 2 | "Am I speaking with {title} {last_name}?" | **fixed**: appended to `opening.on_enter.text`; second ask: `opening_again.on_enter` (type llm, "ask exactly") | all | `render.render` replaces only `{title}` and `{last_name}`; see E.12. |
| 3 | Only yes / that's me / speaking / own name confirms; ask once more; then not_reached/unclear; answer a question first | **route**: extractor `who` (opening) and `confirmed_now` (opening_again); `opening -> always -> opening_again`; `opening_again.max_node_turns = 2 -> outcome_unclear`; **code**: `outcome_unclear` (`fixed_outcome_code`). "Answer a question first": **prompt** (`opening_again.on_enter.prompt`) | EXT-03 | The count of asks is structural (`policy.confirmation.max_asks`). What counts as confirmation is the extractor's call. |
| 4 | Robot/AI question: say digital assistant, continue | **prompt**: `system_prompt` line, opening rules, adapt addition in `identity` | PUB-04 (asked in negotiate) | Never tested at the opening or during identity. |
| 5 | Someone else: say nothing beyond the opening; ask when reachable | **prompt**: prompts.py `third_party_task`; **structure**: step `third_party` has only `schedule_callback` | PUB-02 | |
| 6 | Callback today or next business day, 10:00-19:00, later than now; schedule, then not_reached/callback | **hook**: hooks.py `CALLBACK_PRE` (window from `policy.callback`, dates from `calendar_facts`); **route**: `callback_state == done -> outcome_callback`; **code**: `outcome_callback` | PUB-02 (wed); PUB-02 on fri/holeve expects no_callback | (verified) 19:00 accepted, 19:30 refused, 10:00 refused when now is 11:00, "half past six" = 18:30, "noon" = 12:00. |
| 7 | Outside window: ask once; second time, no callback | **hook**: `CALLBACK_PRE` counter `callback_outside` against `policy.callback.max_asks`; **route**: extractor `third_party_result == no_callback`, goodbye transition `outcome_no_callback_quiet`, turn cap 6 | EXT-04 | (verified) second outside offer produces "do not ask again ... call transition_to_outcome_no_callback_quiet". |
| 8 | Wrong number | **route**: extractor `who == wrong_number` (opening) or `third_party_result == wrong_number`; **code** `outcome_wrong_number` | EXT-01 | |
| 9 | Deceased: "I am sorry for your loss.", ask nothing else | **route** as above to `outcome_deceased`; **fixed**: `hang_up_deceased.terminal.spoken_message` = `policy.third_party.deceased_sentence` + goodbye | EXT-02 | The sentence is spoken after `close_call` ran (see D.4). |
| 10 | Relative may not answer security questions or hear account details | **structure**: no `verify_identity` tool in `third_party`; **prompt** | PUB-02 (husband offers to pay) | |
| 11 | Two questions in order; DOB as YYYY-MM-DD; numeric date is day-month-year | **prompt**: prompts.py `identity_task` lists `policy.identity.questions` in order; **hook**: `VERIFY_PRE` canonicalises dates (`dates.date_parts` with `policy.identity.numeric_date_order`) and digit counts, joins partial answers; `VERIFY_POST` "ask the next question in the order" | every verified case; pieces/in_words/corrects runs | (verified) "14 March" then "1988" -> 1988-03-14; "four four seven one" -> 4471; "14/3/88" -> asks for the year until a four-digit year arrives. |
| 12 | Wrong answer may be re-asked; three wrong in total end the check | **hook**: `VERIFY_POST` reads the bank's `wrong_answers_left`; sets `id_state = failed` at 0; **route** `-> outcome_id_failed` | PUB-03 | The count is the bank's, which is right. Depends on the response field name (E.3). |
| 13 | `hint: day_month_swapped` -> ask for the month as a word; not a wrong answer | **hook**: `VERIFY_POST` (`policy.identity.hint_value`, `hint_instruction`); **prompt** | **untested** | No practice or EXT case triggers the hint. tests/mock_bank.py simulates it, the organisers' mock presumably does. |
| 14 | After three wrong: do not state the debt; app or branch; not_verified/failed | **route** `id_state == failed -> outcome_id_failed`; **fixed**: `hang_up_id_failed.terminal` = `policy.identity.on_fail_sentence` + goodbye | PUB-03 | Flaky in run33/run29: the third answer arrives truncated ("21st of July,"), the model fills the year from the previous answer, the bank says correct. Known residual. |
| 15 | Decline: explain once; second decline or second "what is this about" -> not_verified/declined | **extractor** `identity_signal == declined` (counts "twice" itself) **route** `-> outcome_id_declined`; goodbye transition `outcome_id_declined_quiet`; **prompt** (`policy.identity.decline_rule`) | EXT-05 | The "once"/"twice" count is a model decision. Judge flagged "asked a third time" once (run24). |
| 16 | After both pass, `get_account` | **structure/route**: `identity -> account` on `id_state == verified` or `all_verified == true`; `account` is an `api_request` pre-action | PUB-01 check | Ledger-safe by construction: no `get_account` tool exists before this step. |
| 17 | Collections-team intro; product in words; amount; days late | **code**: render.py `account_code` builds `debt_statement` from `policy.debt_intro_sentence` + `dates.product_facts` spoken lines + `policy.sentences.first_ask`; **fixed**: `negotiate.on_enter.text = {{debt_statement}}` | PUB-01, all | |
| 7-cal | Business days and holidays | **code**: `dates.is_business_day` with `policy.calendar` | PUB-07, EXT-15, holeve cases | |
| 18 | Bands, deadline (nth business day after today), attempts | **code**: `dates.product_facts` (`band_for`, `nth_business_day_after`) -> `product_facts_json`, `attempts_allowed` | PUB-04, EXT-15/17 (deadlines); EXT-10 (early, 1 attempt) | Late band with two flat refusals is **untested in Brief A** (only NW-12 in the variant and PUB-12/EXB-06 in B). |
| 19 | Promise date today or later, business day, not after deadline | **code**: step `resolve_proposal` (`dates.adjust_day`) before the read-back; **hook**: `PROMISE_PRE` blocks past, non-business, after-deadline dates | EXT-09, EXT-17, PUB-04, PUB-07 | (verified) all three blocks. |
| 20 | Weekend/holiday -> next business day | **code** `resolve_proposal` + **hook**, via `policy.date_adjust.non_business_day` | EXT-09, PUB-07 | |
| 21 | Vague period -> ask once -> propose the deadline | **extractor** `last_reply == no_exact_day` **route** `-> offer_deadline` (**code** sets `offer_now`); the single ask is **prompt** | PUB-07, EXT-15 | Works in runs; the "once" is the model's. |
| 22 | "Next weekday" = following calendar week; "this weekday" = current week | **code**: `dates.parse_day_words` / `_weekday_date`; `weekday_table` in the prompt | EXT-16 ("next Friday") | **BUG (verified)**: "next Monday" on Wednesday 14 Oct resolves to 26 Oct, not 19 Oct; "next Tuesday" -> 27 Oct; "next Wednesday" on Thursday -> 28 Oct. Only weekdays later in the week than today are right. See B.1. |
| 23 | After the deadline: say the latest is the deadline, offer it; refusal = flat refusal | **code** `resolve_proposal` (`adjust_day` with `after_deadline = offer_deadline`) + **hook**; refusal counted by `count_refusal` | PUB-04, EXT-17 | |
| 24 | Full amount first; never "how much can you pay?"; agent proposes every amount | **fixed**: first ask inside `debt_statement`; **prompt** (`policy.amount_rules`) | PUB-06 check | |
| 25 | Floor = minimum_payment / instalment_amount | **code**: `dates.product_facts` via `policy.floor_field` | PUB-06, EXT-08 | |
| 26 | Full too much -> floor once, "rest stays overdue"; refuse floor = flat refusal; attempt 2 may repeat the floor on the deadline | **prompt** only for the offer and the sentence; the facts line names the floor | PUB-06 | "Once" and "rest stays overdue" are model decisions. |
| 27 | Own amount in [floor, full] accepted; below floor -> cannot record, offer floor once | **hook**: `PROMISE_PRE` floor block (after the read-back); **prompt** | EXT-07, EXT-08 | No pre-read-back amount check in code (there is no extracted amount). Above the full amount: nowhere. |
| 28 | "Can you make this payment today?" | **fixed** in `debt_statement` (`policy.sentences.first_ask`) | PUB-01 | |
| 29 | A proposed date or amount is never a refusal | **extractor** `last_reply` enum (proposal vs refusal) + **route** | PUB-04 check | |
| 30 | Flat refusal uses one attempt; attempt 1 = last business day of this week (next week if today); attempt 2 = floor on the deadline, late band only | **code**: `dates.attempt1_date` from `policy.attempt1_rule`; `count_refusal` counts against `attempts_allowed`; attempt-2 text in `dates.product_facts` is **hard-wired** ("propose the floor amount X on <deadline>"), not from the policy; **prompt** `policy.persuasion_rules` | EXT-10, PUB-06, PUB-10 | The attempt-2 content is a Brief A rule written into code (E.5). |
| 31 | Attempts used up: stop, no repeats, no_promise/refused | **code**: `count_refusal -> stop_offers` on `refusals_over == yes`; `stop_offers` sets `end_reason = refused` | EXT-10 | (verified) overrides an earlier hardship end reason, see B.4. |
| 32 | Hardship: one sympathy sentence, no persuasion, offer support; accept -> transferred/support; decline -> no_promise/hardship; before 30 and 41; own date still recorded | **prompt** (`policy.special_rules`); **hook** `TRANSFER_POST` -> `transfer_state = done` -> **route** `set_outcome` -> **code** `outcome_code` (`policy.transfers`); **extractor** `end_reason == hardship` -> goodbye transition `wrap_up_hardship` | PUB-05, EXT-13 | "No persuasion attempt" is prompt-only and `count_refusal` can still count the hardship customer's "no". "Hardship but names a date": **untested**. |
| 33 | No discount, waiver, plan, other term | **prompt** (`system_prompt` "never offer anything not in your instructions"; rules text) | PUB-05 check | |
| 34 | Read back product, amount, date; "Do you confirm?"; `create_promise` only after a clear yes | **prompt** (negotiate part 5, `policy.sentences.confirm_question`) + tool description | all promise cases | The consent gate is a model decision; no extracted "confirmed" flag gates the tool. |
| 35 | Change at the read-back -> recheck -> read back again | **route** `resolve_proposal` on new day words + **hook** recheck; **prompt** | EXT-14 (date) | Amount change at the read-back: **untested**. |
| 36 | One promise per product; cannot change or cancel; "change it in the app" | **hook** `PROMISE_PRE` `_same_promise` guard blocks an **identical** repeat only; **prompt** | **untested** | (verified) a second `create_promise` for the same product with another date or amount is **sent to the bank**. See B.2. |
| 37 | "Recorded" only after ok:true; retry once; then no_promise/service_error | **hook** `PROMISE_POST` (`promise_failures` counter, `what_to_do_next`); **code** `outcome_code` (`promise_failures >= 2 -> service_error`), goodbye transition `wrap_up_service_error` | PUB-10 (one failure) | Two consecutive failures never observed end to end; the mock only fails once. |
| 38 | "You will receive a text message confirming this promise." | **hook** `PROMISE_POST` says "then say exactly: ..." (`policy.sentences.after_promise`); **prompt** part 6 | PUB-01 check | Model must still say it; not a fixed line. |
| 39 | Already paid: "one business day to appear", no promise, paid | **extractor** `end_reason == paid` -> `wrap_up_paid` -> **code** `outcome_code`; the sentence is **prompt** | PUB-08 | |
| 40 | Dispute (incl. closed or paid off in the past): no argument, no promise, no_promise/dispute | **extractor** `end_reason == dispute` -> `wrap_up_dispute`; **prompt** | EXT-12 | "Will not pay anything" can be classified `refusal` first and trigger `count_refusal` (B.4). |
| 41 | Restructuring -> transfer restructuring -> transferred/restructuring | tool `transfer_to_agent` (queues from the API file) + **hook** + **code** `outcome_code` | PUB-09 | |
| 42 | Human: ask once; insist -> transfer general -> transferred/human; before and after verification | tool in `identity` and `negotiate`; **prompt** ("ask once" is the model's) | EXT-11 (before verification) | After verification: **untested**. |
| 43 | Scam: customer service number; continue | **prompt** (`system_prompt`, adapt additions) | EXT-06 | |
| 44 | Unknown information: say you do not have it | **prompt** (`system_prompt`) | **untested** (asks_back style touches it) | |
| 45 | Twice "do not want to talk": no_promise/refused after verification, not_verified/declined before | **extractor** (`end_reason == refused` / `identity_signal == declined`, counts "twice"); **prompt** | EXT-18 (after) | Before verification: **untested** (EXT-05 declines by question, not by "don't want to talk"). |
| 46 | Exactly one `close_call`, last, outcome and reason from the table; a transfer after a promise closes as transferred | **structure**: step `close` (api_request pre-action) on every exit path; **hook** `CLOSE_PRE` fills `outcome`/`reason` from vars, recomputes via `outcome_code` for verified calls, drops `reason` for `policy.no_reason_outcomes` | all | (verified) transfer after a promise -> transferred/restructuring; empty vars -> `policy.outcomes.unclear` outcome without a reason. "Transfer after a recorded promise" never run. |
| 47 | Thank and say goodbye before `close_call` | Model exits: **prompt** + goodbye transitions (`is_tool_call`) -> `wrap_up*` -> `end_quiet` (silent terminal). Code exits (turn caps, callback booked, wrong number, deceased, id failed, `stop_offers`, transfers): terminal `spoken_message` is spoken **after** `close_call` | all | Order is inverted on code exits; judges have not flagged it so far (EXT-01/02, PUB-03 pass). See D.4. |

### Brief B (multi-product)

The current render keeps the deterministic negotiate routes only when `product_count == "1"` (render.py `stops`), and `account_code` sets `attempts_allowed = "per_product"`, so `count_refusal`, `offer_deadline` and `resolve_proposal` never fire for two or three products (verified by rendering the fixture policy with `multi_product.enabled = true`). Everything multi-product is therefore prompt plus hooks.

| B rule | Where it lives | Case | Note |
|---|---|---|---|
| 1 one to three products | **code** `account_code._flat_list` + `product_facts` per product | PUB-11/12/13 | (verified) two products -> `product_count 2`, per-product deadlines 2026-11-02 and 2026-10-23. |
| 2 state every product first | **fixed** `debt_statement` (one sentence per product) | PUB-11 | |
| 3 band and deadline per product | **code** `product_facts` | PUB-13 | |
| 4 "all today?" once, then product by product, attempt 1 each | **fixed** `policy.sentences.first_ask_multi` in `debt_statement`; rest **prompt** (`policy.multi_product.rules`) | PUB-11/12 | |
| 5 attempts per product | **prompt only** (refusal counter inert) | PUB-12 check | Model counts. |
| 6 one date for all, clamp per product, say so in the read-back | **hook** `PROMISE_PRE` blocks the late product's date after confirmation and asks for a new read-back; the clamp in the first read-back is **prompt** | PUB-13, EXB-04 | (verified) p2 on 30 Oct with deadline 23 Oct -> blocked; the model must then re-read back, so "one confirmation" may fail. |
| 7 one read-back, then one `create_promise` per product | **prompt** + tool description | PUB-11 | |
| 8 `add_note` per product without a promise, with the reason | tool `add_note` (enum from the API file) + **hook** `NOTE_PRE/POST` (`notes_recorded`) + **prompt** | PUB-12, EXB-02/03/05/06/07 | |
| 9 dispute or paid on one product does not end the call | **prompt only** | EXB-02, EXB-07 | |
| 10 restructuring: recorded promises stay, unrecorded not; no notes on any transfer | **code** `outcome_code` (transfer wins); "no notes" **prompt only** | EXB-01 | |
| 11 `create_promise` fails twice: keep the others, note service_error | **hook** `PROMISE_POST` `service_next` (`note_reason` of `service_error`) | **untested** | |
| closing | **code** `outcome_code`: promise wins; else all-paid -> paid; else first non-paid note in `get_account` order | EXB-03, EXB-05 | (verified) [paid, dispute] -> dispute; [refused, paid] -> refused; [paid, paid] -> paid. |

**Evidence gap on B**: results/log.jsonl has no run of the B cases (PUB-11..13 or EXB-01..07) at all; the only B export (brief-a_brief-b.workflow.json, 01:16) has 22 steps and predates the refusal counter, day resolution, wrap-up steps and the close step. The multi-product path of the current builder has never been exercised on the platform. The README says hidden customers can have up to three products.

---

## B. Gaps

Ranked by likelihood x impact under 3-of-3.

1. **Rule 22 is wrong in code for most weekdays** (verified in `dates._weekday_date`). "next Monday" said on Wednesday 14 October becomes 26 October (a holiday, then clamped to 27 October by `adjust_day`), the brief and the prompt's own `weekday_table` say 19 October. Same for any "next <weekday>" whose weekday is earlier in the week than today, on any day of the week. A hidden customer who says "next Monday", "next Tuesday" or "next Wednesday" on a Thursday gets a wrong ledger date in 3 of 3 runs. The callback hook's `_day` in hooks.py has the same arithmetic (less harmful: a callback must be today or the next business day). Fix: Monday of the current week + 7 + weekday for "next"; current-week weekday for "this"/bare (today when it is today). tests/test_dates.py `DayWords` still passes with that formula (checked by hand: Wed 14 -> next Friday 23; Fri 16 -> next Friday 23).

2. **Rule 36 has no code home**: `PROMISE_PRE._same_promise` blocks only an identical repeat. A second `create_promise` for a product already in `promises_recorded` with a different date or amount goes to the bank (verified). Hidden customer: "Actually, make that the 21st" after the agent said "recorded". Brief: the promise cannot be changed; say they can change it in the app. Ledger expected: the first promise only. Today the model obeys the prompt most of the time; one slip is a second ledger row and a fail. The API file itself says "One per product", so a guard that blocks any second promise for a known `product_id` is derivable from the API, not from a brief.

3. **Brief B logic is prompt-only** (see the B table) and untested with the current code. Hidden customers with two or three products: every attempt count, every per-product date and the single read-back are model decisions. With one product the same decisions are in code.

4. **Refusal counter versus special situations** (verified): `count_refusal` counts any `last_reply == refusal`; `stop_offers` then writes `end_reason = refused` even when `end_reason` was already `hardship`. Hidden customer, early band: "I lost my job, I can't pay anything" (extractor may say `refusal`), then "No, I don't want the support team" (`refusal` again) -> `refusals_over` -> no_promise/**refused**. Brief: no_promise/**hardship**, no persuasion attempt. The same pattern turns a dispute plus "I won't pay" into a persuasion attempt (judge check "no persuasion attempt is made" in EXT-12). PUB-05 and EXT-12 pass today because the extractor usually picks `hardship`/`other`; the route exists to go wrong.

5. **Response field names of `verify_identity` are assumed** (verified): if the hidden API renames `all_verified`, `verified`, `wrong_answers_left` or `hint`, `VERIFY_POST` never sets `id_state`, the `identity -> account` route never fires, and every customer ends not_verified. Same for `get_account`'s `products` list and its `product_id`/`type`/`past_due`/`days_late` keys in `account_code` and `dates.product_facts`. See E.

6. **Request field names in hooks are assumed**: `PROMISE_PRE` reads `amount`, `date`, `product_id`; with a renamed amount field every promise is blocked as "below the floor" because `float(None or 0)` is 0 (verified). `CLOSE_PRE` writes `outcome`/`reason`; `CALLBACK_PRE` reads `date`/`time`; `VERIFY_PRE` reads `field`/`answer`; `TRANSFER_PRE` reads `queue`. The tool *bodies* are generated from the API file, so the model fills the new names; the hooks read the old ones.

7. **Renamed `close_call` fields or a path prefix crash the builder** (verified): `render.tool` does `body["outcome"]` and `spec["paths"]["/" + name]`; `KeyError` propagates, and build.py's fallback `render.render({}, spec)` raises the same error before any `save_workflow`. A `$ref` request schema renders an empty body: no model-filled fields, no crash, silent total failure (verified).

8. **Attempt-2 content is hard-coded** in `dates.product_facts` ("after a second flat refusal propose the floor amount X on <deadline>"), which is Brief A rule 30. A hidden brief whose second attempt is different gets contradictory instructions (facts line vs `policy.persuasion_rules`). With three attempts the facts line still says STOP after the second. With no floor field for a product type the line reads "floor amount None" and "propose the floor amount None" (verified).

9. **Schema shapes the policy cannot hold**: a deadline not of the form "nth business day after today" (calendar days, a fixed date, "end of next month"); a callback window other than today/next-business-day with one from/to (for example "within three business days", "any weekday 9-5"); a confirmation question that uses `{first_name}` (only `{title}` and `{last_name}` are substituted, render.py `render` and prompts.py `opening_task`; a stray `{first_name}` would be spoken aloud); an identity field of "year" type given as two digits (the variant memo asks for 19xx expansion; the hook asks for "the rest" and concatenates, "79" twice becomes "7979", verified); a product type with no floor; a reason required on the promise outcome is representable, a different `close_call` field set is not.

10. **Rules with no practice case** (ledger-relevant first): rule 13 hint; late-band two-attempt refusal (A); rule 36 change after recording; rule 37 double failure; rule 42 after verification; rule 45 before verification; rule 32 with a named date; amount change at the read-back (35); transfer after a recorded promise (46); B rule 11; B rule 10 "no notes" after a note was already written; any customer on a Saturday or Sunday `now` (calendar_facts on Sat 17 Oct gives attempt-1 date 23 Oct and offers a "today" callback window, verified; whether the organisers run weekend days is unknown).

11. **In-words day numbers are not parsed** (verified): "the twenty-second of October", "October twenty-second", "the sixteenth" return None from `parse_day_words`; "Friday the sixteenth" works. The model then computes the date itself, which is the failure class the code was built to remove. The README says hidden customers say dates in words.

12. **Amounts are never canonicalised**: no extracted amount, no pre-read-back check; `PROMISE_PRE` ignores a non-numeric amount ("four hundred and twenty", "1,250") and sends it unchanged (verified). An amount above the full past-due is not capped (brief silent; a bank would cap at the past-due).

---

## C. Edge cases a bank QA team would script

"Handled" means the outcome is decided by code, a hook or a route; "model" means the dialogue model or the extractor decides; "no" means the current workflow produces the wrong ledger or has no path. "(L)" = confirmed locally by executing the rendered code/hook; "(R)" = by reading the workflow and code; "(run)" = a practice case exists and passes.

| # | Script | Brief: expected ledger / transcript | Current workflow | How verified |
|---|---|---|---|---|
| 1 | Changes the amount at the read-back ("make it 200, not 300") | Rule 35: recheck against floor/full, read back again; one promise 200 | model: no extracted amount; floor only checked in the hook at call time | R |
| 2 | Pays part today and the rest next week (same product) | Rule 36: one promise per product; the agent should explain and record one (brief does not say which) | **no**: second `create_promise` with another date is sent; two ledger rows | L |
| 3 | Two products, promises one, refuses the other | B8: one promise, one `refused` note | model (B prompt only); never run with current code | R |
| 4 | Gives the phone digits when asked for the date of birth | Not a wrong answer; ask again | handled: `VERIFY_PRE` finds no day/month/year in "4471", blocks and asks (not counted wrong) | L (date_parts) |
| 5 | "I already paid" said during identity, before verification | Finish verification first; then rule 39 | model (no identity-step instruction for it) | R |
| 6 | Asks to be called back on a holiday or a Sunday | Rule 7: ask once, then no_callback | handled: `CALLBACK_PRE` accepts only today or `callback_next_business_day` | L |
| 7 | Date after the deadline, then accepts the deadline | Rule 23: promise on the deadline | handled | run (EXT-17, PUB-04) |
| 8 | After "recorded", says the date read back was wrong | Rule 36: cannot change; app; ledger keeps the first promise | **no** guard; prompt only | L |
| 9 | "Is this a scam?" mid-identity | Rule 43, continue | handled by prompt | run (EXT-06) |
| 10 | Hangs up during the read-back | Brief: every call ends with `close_call`; ledger: no promise, call closed | **no**: `close_call` runs only from the `close` step; a customer hang-up leaves the ledger unclosed | R |
| 11 | "Yes" to the name but gives a different name | Rule 3: not a confirmation; treat as someone else or ask again | model (extractor `who`) | R |
| 12 | "Next Monday" said on a Wednesday | Rule 22: Monday of the following week (19 Oct) | **no**: 26 Oct, clamped to 27 Oct | L |
| 13 | "Tomorrow" said on a Friday | Rule 20: Saturday -> Monday | handled (`adjust_day`) | L |
| 14 | "End of the month" then "the 30th" in the late band (deadline 23rd) | Rules 21, 23: offer the deadline | handled: `offer_deadline` then `resolve_proposal` -> deadline | L (parse "the 30th") + run (EXT-15/17 pieces) |
| 15 | Hardship, then "I can pay 100 on Friday" (floor 126) | Rule 32 + 27: sympathy, no persuasion, "100 cannot be recorded", floor once | model; `count_refusal` may count the "no" (B.4) | R, L |
| 16 | Insists on a human after verification, after a promise was recorded | Rule 46: transferred/human, promise stays | handled in `outcome_code` (transfer wins); transfer tool in negotiate | L (outcome_code); never run |
| 17 | Flat refusal, late band | Rule 30: Friday full, then floor on the deadline, then no_promise/refused | handled by `count_refusal` (n > 2) + facts text | R; untested in A runs |
| 18 | Full too much, refuses the floor, early band | Rule 26/30: floor once; refusal is attempt 1 (floor on Friday); then stop | handled: counter; the "amount in play" is the model's | R |
| 19 | Offers more than the full amount | Brief silent | hook does not cap; recorded as said | L |
| 20 | Confirms with "sure" / "okay" | Rule 34: clear yes | model | R |
| 21 | DOB with a two-digit year, repeated ("14/3/88", "88") | Rule 11 | partly: hook asks for the year until four digits; with a stubborn persona, 14 turns -> not_verified/declined | L |
| 22 | Amount in words at the promise | ledger needs a number | model converts (in_words run passed 21/21 once); hook does not check | L |
| 23 | Relative asks twice what it is about, then gives a time | Rule 5/6 | handled | run (PUB-02) |
| 24 | "Don't want to talk" twice before verification | Rule 45: not_verified/declined | extractor counts | R; untested |
| 25 | "I paid that loan off last year" | Rule 40: dispute, not paid | extractor (`dispute` vs `paid`) | run (EXT-12 similar) |
| 26 | `create_promise` fails twice | Rule 37: no_promise/service_error, "could not record" | handled in code; cannot be produced with either mock (one failure only) | L (outcome_code) |
| 27 | B: one date for both, after one deadline | B6: read-back names both dates, one confirmation | partly: hook clamps after the confirmation, forcing a second read-back | L |
| 28 | B: restructuring after one promise recorded, after a note was written | B10: transferred/restructuring, no notes | outcome in code; "no notes" prompt only; a note already written cannot be undone | R |
| 29 | Talkative relative plus two outside-window offers | Rule 7 | `third_party.max_node_turns = 6` -> no_callback (right by luck); a callback case with `asks_back` is at 5-6 turns | R |
| 30 | Customer says the full amount today but the agent's read-back is interrupted by "wait, which card?" | Rule 44, 34 | model; `offer_now` may be stale | R |

---

## D. Honesty and judge risks

1. **"Recorded" is hook-gated** (`PROMISE_POST` only writes "Recorded ... say exactly ..." on `ok == true`); "booked" and "transferred" likewise (`CALLBACK_POST`, `TRANSFER_POST`); the system prompt forbids claiming otherwise. The identical-repeat guard says "ALREADY recorded" truthfully. Good.

2. **Bank rejection with no counter**: `PROMISE_POST` on `ok:false` with an `error` and status < 500 says "Correct the values and CALL create_promise again" with no limit. Tool calls do not count as user turns, so a persistent rejection (a hidden mock that dislikes a date format) can loop inside one turn. Honesty is kept (never says recorded) but the call stalls. Cheap counter.

3. **The text-message sentence is model-spoken**, not a fixed line; the judge checks it (PUB-01). Observed always said so far.

4. **Rule 47 order on code exits**: on `outcome_callback`, `outcome_wrong_number`, `outcome_deceased`, `outcome_id_failed`, `stop_offers`, `set_outcome` (transfers) and the turn caps, the farewell is the terminal's `spoken_message`, spoken after the `close` step ran `close_call`. The judge sees system events (its reasons quote them). Not flagged in any review so far across EXT-01/02, PUB-03, EXT-10; keep as a known risk, do not restructure now.

5. **Double goodbye** on the same code exits when the hook already told the model to "thank them and say goodbye" (`CALLBACK_POST`, `TRANSFER_POST`): the terminal repeats "Thank you for your time. Goodbye." The paper's rubric penalises repeated frames; no local judge has.

6. **"recorded" in the opening**: a judge failed NW-13 because "This call may be recorded" was said before the successful `create_promise` (check: "does not say 'recorded' before a successful call"). Rule 1 forces the word; nothing to fix, expect this variance on PUB-10-like customers.

7. **"inconclusive" verdicts**: results/run34-rep1.json (the run in progress, first repetition) shows 4 of 21 cases with judge outcome `inconclusive` and reason text "All criteria met" (EXT-01, EXT-04, EXT-09, EXT-15); tools/run_cases.py counts anything but `pass` as a fail. The organisers' scorer may differ; the local pass rate understates when this happens.

8. **Goodbye without a transition**: `conversation_done == yes` routes to `wrap_up`, whose `outcome_code` falls back to `refused` when no promise and `end_reason == none`. A "paid" customer whose `end_reason` the extractor missed closes as no_promise/refused.

9. **Prompt text a strict judge could misread**: negotiate carries every brief rule verbatim plus a rewritten copy (`policy.date_rules` etc.), so the model sees "close as no_promise / refused"-style sentences twice in different words; harmless to the judge, but long. The system prompt lists "the product (credit card, personal loan, car loan)" as forbidden words, so the model will not name product types before verification (right).

10. **Stale `offer_now`**: `resolve_proposal` writes a read-back instruction that persists until a promise is recorded or a refusal is counted; after an unrelated question the model still sees "Read back <date> and record exactly ...". Could produce a read-back the customer did not ask for.

---

## E. Builder robustness for a hidden brief

Pointers are to builder/ files. Severity: how a hidden brief with that shape would end.

1. **Builder crash, no workflow saved** (verified): render.py `tool()` indexes `spec["paths"]["/" + name]["post"]` and, for `close_call`, `body["outcome"]` and `body["reason"]`. A path prefix (`/tools/close_call`), a different method, or a renamed outcome/reason field raises `KeyError`; build.py catches the first `render.render(policy, spec)` but the fallback `render.render({}, spec)` raises too, before `save()`. A `$ref` request schema (`components/schemas`) renders a tool with an empty body (verified), so the model has nothing to fill. The hackathon allows "fixing a crash on an unexpected table format" after 20:00, but a crash at 20:05 costs the clock and the trace.

2. **Request field names inside hooks** (hooks.py `PROMISE_PRE`, `CLOSE_PRE`, `CALLBACK_PRE`, `VERIFY_PRE`, `TRANSFER_PRE`, `NOTE_PRE`): hard-coded `amount`, `date`, `product_id`, `outcome`, `reason`, `time`, `field`, `answer`, `queue`. Verified: renamed amount -> every promise blocked "below the floor". Renamed date -> every promise blocked "could not be read". Renamed outcome/reason in `close_call` -> `CLOSE_PRE` adds keys the bank ignores and the real ones stay as literal placeholders (the engine drops a field that is exactly `{{x}}`, so the bank receives no outcome).

3. **Response field names** (hooks.py `VERIFY_POST`, render.py identity routes, `account_code`, dates.py `product_facts`): `all_verified`, `verified`, `wrong_answers_left`, `hint`, `ok`; `products[]` with `product_id`, `type`, `past_due`, `days_late`. Verified: a response `{"passed": true, "attempts_left": 3, "fully_verified": true}` gives `id_state = None` and the instruction "WRONG ANSWER ... None wrong answers left". The identity route tests `id_state`, `id_all_verified` and `verify_identity_response.data.all_verified`; all three depend on the same name. The spec's 200 response schema names the fields; nothing reads it.

4. **Identity question kinds** (hooks.py `VERIFY_PRE`): a question is "datelike" if its format mentions yyyy/date or the field name contains date or birth (but not year); "digits" if the format says "N digits"; anything else passes through untouched. Three questions: fine (`VERIFY_POST` says "next question in the order"). Postcode or mother's maiden name: pass-through, the model must format (the Northwind run shows it does: "B33 8TH" -> "B338TH"); in `pieces` style ("B33" then "8TH") the hook sends each half as a full answer (verified) and the bank counts a wrong answer; with `max_wrong_total = 2` that customer is lost. A year field given as two digits: asked for "the rest", a repeat concatenates to four wrong digits (verified).

5. **Bands and attempts** (dates.py `product_facts`): one band or three bands fine (`band_for`); `attempts` 0, 1, 2 have texts; 3 or more still say STOP after the second; attempt 2 is hard-wired as "floor on the deadline" (Brief A rule 30, a hard-coding the project's own rules forbid). `attempt1_rule` supports last_business_day_of_week, next_business_day, nth_business_day, deadline, none; "the same day next week" or "in 3 calendar days" cannot be expressed and normalize.py `problems()` rejects any other value, forcing the repair call to pick one.

6. **No floor / unknown product type**: `floor` None -> "floor amount None" and "propose the floor amount None" in the prompt (verified); `PROMISE_PRE` skips the floor check (fine). A product `type` not in `policy.product_words` is spoken as the raw type with underscores replaced; `card_last4` missing -> `str.format` KeyError is caught and the template stays literal ("credit card ending {card_last4}").

7. **Deadline and callback shapes** (policy_schema.json): deadline only as `deadline_business_days` (integer); callback only as `days` tokens today/next_business_day plus `from`/`to`; `date_adjust` only next/previous business day. Anything else is forced into these or lost; the Northwind variant happened to fit.

8. **Currency and number formats**: `dates.money` prints bare numbers ("637.50"); no currency symbol anywhere; thousands separators or words in the model's `amount` argument are not normalised and skip the floor check (verified).

9. **Enum renames** are handled where they come from the API file: tool bodies (`tool()` copies `enum`), queues (`policy.transfers`), outcomes and reasons (`policy.outcomes`, `end_reasons`, `no_reason_outcomes`), note reasons. `outcome_code` keys on the schema's internal keys (`refused`, `paid`, `service_error`), which the normalize prompt instructs the model to use regardless of the brief's words; the variant run confirms (declined/settled/system_error mapped correctly).

10. **Multi-product**: see A/B; with `product_count != 1` nothing deterministic in negotiate.

11. **normalize.py `problems()`** demands all eight situations (`unclear`, `callback`, `no_callback`, `wrong_number`, `deceased`, `id_failed`, `id_declined`, `promise`) and an `attempt1_rule`; a brief without, say, a deceased rule forces the repair call to fill one (the prompt says never invent, so it may leave it empty and the build raises "policy still incomplete" -> build.py renders from `{}`, which still saves a generic agent). That generic agent has empty outcomes: `CLOSE_PRE` would send `outcome = ""`.

12. **Call-variable placeholders** (render.py `render`, prompts.py `opening_task`): only `{title}` and `{last_name}` are turned into `{{...}}`. A confirm question built on `{first_name}` (plausible for a credit union, "Am I speaking with Ava?") is spoken with the literal braces.

13. **Language**: `policy.language` only changes "Speak X" in the system prompt; hooks' `what_to_do_next`, the default goodbye and the facts text are English.

14. **Submission hygiene**: `.gitignore` excludes `*.workflow.json` and `traces/`. The submission requires the exported workflows and traces committed. Either `git add -f` them or edit .gitignore before 20:00. `work/` (policy.json per build) is also ignored, so the reviewer agent cannot see the policy that produced the agent unless the trace carries it (it carries a summary and every rule home, which is adequate).

---

## F. Bank approval readiness (one page)

| Approver | What they would ask | Evidence in this repo today | Missing |
|---|---|---|---|
| Collections business owner | Does it get promises inside policy, and how often does it get the call right? | results/log.jsonl: 21/21 x3 on four of the last six full runs, 20/21 and 19/21 on the others; cases-fri 20/21, cases-holeve 18/19; run_cases prints promised amounts per ledger | No late-band two-attempt evidence, no multi-product evidence with current code, no promise-rate or call-length KPIs, no production sampling plan |
| Compliance / conduct | Every rule has a home; disclosures are fixed; vulnerable customers handled; nothing offered outside policy | Section A matrix; fixed opening/recording line; hardship route with support transfer; judge checks per case; "never offer anything not in your instructions" | Vulnerability limited to the brief's three triggers; no complaint path (a "I want to complain" customer is improvised); no affordability conversation by design of the brief; rule 26's "rest stays overdue" is prompt-only |
| Legal | Recording consent, third-party non-disclosure, promise terms read back | Fixed recording line; structural non-disclosure (no account tools before verification, score.py checks it); read-back before every write | Read-back consent is a model judgement, not an extracted explicit yes; promise terms (one per product, cannot change) not enforced in code |
| Data protection | What personal data flows where, retention | Synthetic data only; secrets in env.sh (gitignored); results hold customer ids, not answers; traces hold no keys | DOB parts persist in `vars` (`id_partial_*`) for the whole call on Freya; the brief (bank policy) is sent to a third-party model (Claude) at build time; no DPIA, no retention statement for Freya transcripts |
| InfoSec / third-party risk | Auth, key handling, code executed where | One key per team; HTTPS; hooks are plain Python in Freya's sandbox, no network from code; builder isolates its working folder (build.py `isolate`) | Bank tool API has no auth by design ("customer_id is the secret"); no key rotation; no review of what Freya logs |
| Model risk / AI governance | Which decisions are model decisions; how stable; change control | Section A (home per rule); builder model pinned (llm.py `claude-opus-5-5`); agent model fixed by the platform; reruns measured; tests/check_consistency.py exists | Consistency check never run (no trace); the adapt stage appends model-written prompt text that differs per build (uncontrolled prompt change, logged in the trace); no acceptance thresholds; judge variance (~3%) and "inconclusive" verdicts unquantified |
| Operational risk | What happens on faults, timeouts, hang-ups | `get_account` retried twice; promise retried once with honesty guard; builder stops inside 27 minutes and saves early; exit paths all reach `close_call` | A customer hang-up leaves the ledger unclosed; a bank rejection loop has no cap; no runbook for a crashed build at 20:00 (and E.1 shows one) |
| Internal audit | Reproducibility and trace | traces/<slot>-<start>.log with start/end, every model call (model, purpose, seconds, cost), workflow/agent ids, steps/tools, rule homes, ambiguities; export right after each run | Exports and traces are gitignored (E.14); policy.json per build is gitignored; no record that the 21-case suite was run against the exact exported version (log has agent id and time only, not the workflow version) |

---

## G. Top 10 actions, ranked

Time now 13:30; hidden briefs at 20:00. "Safe now" means local unit tests cover it and the change is in the path the 21 cases already exercise, so one `--reps 3` run (about 10 minutes) confirms no regression. Nothing below writes a brief value into code; AGENT_LLM untouched; the agent still calls only the bank API.

| # | What | Why (hidden-customer failure prevented) | Effort | Regression risk | Now? |
|---|---|---|---|---|---|
| 1 | Fix `dates._weekday_date` so "next <weekday>" is the weekday of the following calendar week and "this"/bare is the current week; mirror in hooks.py `CALLBACK_PRE._day`; add the Wed/Thu "next Monday" cases to tests/test_dates.py | Any "next Monday/Tuesday/Wednesday" promise is a wrong ledger date in 3 of 3 (B.1) | 15 min | Low (unit tests; EXT-16 covers Friday) | **Yes** |
| 2 | Make render.py `tool()` and build.py survive an unexpected API file: resolve `$ref` under `components`; find each path by suffix match on the tool name; for `close_call` pick the outcome/reason fields by name match with a fallback; wrap the bare fallback render in try/except so `save()` always runs; add a unit test with a mutated spec | A renamed field or a `$ref` schema today means no workflow at all (E.1) | 40 min | Low (new branches only fire on specs that differ) | **Yes** |
| 3 | Read the request field names from the API file at render time and pass a name map into the hooks (hooks.py `fill` already takes values); in `PROMISE_PRE` treat a missing amount as "not checked", never as 0 | Renamed `amount`/`date`/`outcome` kills every promise or every close (E.2) | 45 min | Medium: touches the happy-path hooks; tests/test_render.py exercises them | Yes, with a `--reps 3` run after; if no time, do only the "missing amount is not 0" line (5 min) |
| 4 | Same for response names in `VERIFY_POST` and the identity routes: take `all_verified`/`verified`/`wrong_answers_left`/`hint` from the spec's 200 schema with the current names as default; substring fallback ("all"+"verif", "left"/"remaining") | Renamed verify response means every customer not_verified (E.3) | 40 min | Medium | Yes if 2 and 3 are done first; otherwise skip |
| 5 | `PROMISE_PRE`: block any `create_promise` whose `product_id` already has a recorded promise, with "already recorded; the customer can change it in the app" (justified by the API's "One per product"); update the test line in tests/test_render.py that currently asserts a second date is not blocked | Rule 36 and B7 ledger duplicates (B.2, C.2, C.8) | 10 min | Low | **Yes** |
| 6 | Build Brief B (`briefs/brief-a.md briefs/brief-b.md tools/openapi.json`) with the current builder and run PUB-11..13 plus tests/extra-cases-b.json once, after the running simulation ends; fix only crashes | The multi-product path has never run on the current code; hidden customers can have three products (A, B.3) | 25 min wall clock, one simulation | None (test only) | **Yes**, first free slot |
| 7 | Ordinal and number words in `dates.parse_day_words` ("twenty-second", "the sixteenth", "first" to "thirty-first"), unit-tested | In-words dates fall back to model arithmetic (B.11) | 20 min | Low | Yes |
| 8 | `count_refusal`: do not count when `end_reason` is already a special key; `stop_offers`: keep an existing hardship/dispute/paid `end_reason` | Hardship or dispute customers closed as refused or persuaded (B.4, C.15) | 10 min | Low-medium (changes refusal path; EXT-10/12/13, PUB-05 cover it) | Yes, with `--only` on those four then `--reps 3` |
| 9 | Cap the "bank rejected, correct and call again" loop in `PROMISE_POST` at two, then the service-error path; raise `third_party.max_node_turns` from 6 to 10 | Stalled calls and a talkative relative closed as no_callback (D.2, C.29) | 10 min | Low | Yes |
| 10 | Submission hygiene: un-ignore or force-add `*.workflow.json` and `traces/`; run tests/check_consistency.py once on Brief A and note the result in README; write the 20:00 runbook (exact command, what to do if normalize or render raises) | Submission rejected or trace unverifiable (E.14, F audit row) | 15 min | None | **Yes** |

Not now: changing the exit-path order so the farewell precedes `close_call` on code exits (D.4), a lifecycle `close_call` backstop for hang-ups (C.10; the team already found post-call analysis unreliable), extracting an amount for a pre-read-back check (B.12), moving the attempt-2 rule into the policy schema (E.5: it needs a normalize prompt change and a repair of `product_facts` text, and the late-band path has no A test to catch a regression), and any prompt rewording for judge taste. Each of these changes the path every passing customer takes with no time to measure three repetitions.

Also worth knowing before 20:00: the hidden brief ambiguities the normalize stage lists go only to the trace; nobody reads them during the run. Read them in the first two minutes of each hidden build and, if one says "the brief does not say X, resolved as Y", decide whether Y matches the brief before the self-test slot is spent.
