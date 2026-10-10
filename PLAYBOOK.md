# Build the Builder: Playbook

Kit v3 · Freya × YC hackathon, 10–11 October 2026 · All times are Istanbul time (UTC+3)

This file replaces the guide written before the kit was released. Everything here is based on the kit, the hackathon page and the organizers' email. Where something is a proposal or not yet tested, it says so.

---

## 0. In one minute

- **What you build:** a program that reads a bank's brief and its tool API file and, with no manual step, creates a phone agent on Freya. The agent is a Freya **workflow**: a graph of steps. Command shape: `python3 builder/build.py <brief.md> [more brief files] <openapi.json>` (Brief B needs Brief A, and raw material may arrive as several files).
- **What is scored:** the phone agent, on 60 hidden customers (2 hidden briefs × 30). A customer passes only if the bank's records are exactly right **and** a judge model finds no policy or honesty problem, in **all 3 runs**, on several calendar days. No partial credit.
- **What is fixed:** the phone agent's model (`experimental-5`, set in `freya.py`). Your builder may use any model.
- **Limits:** 30 minutes per brief including self-tests · 200 workflows per workspace, updated in place · 1 simulation at a time.
- **Deadline:** hidden briefs open **Sunday 20:00**, submission closes **Sunday 23:00** (17:00 and 20:00 UTC on the hackathon page). The builder must be finished before 20:00.
- **How to win:** put every rule where it is most reliable (arithmetic in code, tool results interpreted by hooks, call flow in routes, judgement in short prompts) and test the rare situations, not only the 13 public cases.

---

## 1. The problem

### Input

- **Brief file(s).** Practice: Brief A (one late product, 47 numbered rules) and Brief B (up to three products, builds on A). Hidden: two briefs for the same kind of call with different rules: other numbers and limits, other identity questions, another outcome table, another calendar. One is a clean specification. The other is raw bank material: an email, a policy extract, a memo that changes it, a code list.
- **Tool API file** (OpenAPI). The seven tool names stay the same: `verify_identity`, `get_account`, `create_promise`, `add_note`, `schedule_callback`, `transfer_to_agent`, `close_call`. Their fields and allowed values can change.

### Output

- A workflow saved with `freya.save_workflow(slot, workflow)`: it creates the workflow once, then updates and publishes it. Use **one slot per brief** (the brief's file name), and a separate slot for a second run, so one run never overwrites another.
- An export with `freya.export_workflow(workflow_id, "<brief>.workflow.json")`, taken **right after each run** into a file named for that run. The organizers load this file into their own workspace, so **what you export is what they score**.
- A **trace** of the run (section 3).

### The call

Freya Bank calls a customer who is late on payments:

1. Opening: a digital assistant from Freya Bank, the call is recorded.
2. Is this the right person? If someone else answers: say nothing about the account, try to book a callback.
3. Identity: security questions checked with `verify_identity`.
4. State the debt: `get_account`, then product, amount and days late.
5. Try to get a payment promise inside the rules on dates and amounts.
6. Close with exactly one `close_call` carrying the right outcome and reason.

### Call variables

Every call starts with `customer_id`, `first_name`, `last_name`, `title`, `now`. All date rules use `now`, never the real clock. Practice cases run as if on **Wednesday 14 October 2026, 11:00**. The hidden test runs on **several calendar days**.

### Customers talk like people

Hidden customers give numbers in two parts, correct themselves, chat about other things, ask questions back, and say amounts and dates in words. `run_cases.py --style pieces | corrects | talkative | asks_back | in_words` simulates each of these.

---

## 2. How a customer is scored

| Check | Who checks | What must hold |
|---|---|---|
| **Outcome** | A script reading the bank's ledger | `close_call` outcome and reason match. Every promise (product, amount, date) matches and is recorded once. Notes, callbacks and transfers match. `close_call` is the last tool call. No `get_account` or `create_promise` before identity is verified. No identity or account tools when the right person was not reached. |
| **Policy** | Judge model reading the transcript | The conversation stayed inside the brief, judged against checks listed for that customer. |
| **Honesty** | Judge model | The agent never says a promise is recorded when the call failed. |

- **Score** = customers passed / 60. A customer counts only when all 3 runs pass. A correct refusal (for example a recorded dispute) counts as a pass.
- **Tie-breakers:** total promised amount on passed customers, then shorter total build time (from your traces), then earlier submission.
- **Verification:** for the top ten, the organizers clone your commit, rerun the builder on the same briefs and compare with your trace. Entries whose rerun scores clearly lower are removed. A reviewer agent checks every trace against your code. So the builder itself must be **consistent**, not lucky.

---

## 3. Rules and limits

| Item | Value |
|---|---|
| Build time | 30 minutes per brief, including self-tests |
| Workflows | 200 per workspace (hackathon page and README). One slot per brief and run, updated in place |
| Simulations | 1 at a time per workspace. A 10-customer run takes 3 to 11 minutes |
| Phone agent model | `AGENT_LLM` in `freya.py`. Never change it |
| Builder model | Any; you pay for it |
| What the agent may call | Only the bank's tool API. Code steps and hooks inside the workflow are allowed and expected |
| After hidden briefs open | Bug fixes only. Nothing from a hidden brief (rules, values, names) may go into code or prompts. Fixing a crash on an unexpected table is fine |
| Manual steps | None, and no hand edits to the created agent |
| Platform | Do not probe or load-test it. One key per team |
| Trace contents | Start and end time; each model call (model and a one-line purpose); what was created on Freya (workflow id, agent id, step and tool counts); each self-test and its result. Plain text. No API keys |
| Submission form | `team`, `repo`, `commit`, `run_command`, `workflows` (hidden-1, hidden-2 paths), `traces` (hidden-1, hidden-2 paths). Steps arrive by email before 20:00 Sunday |

---

## 4. Freya platform essentials

Source: `docs/workflow-format.md`, `docs/tools-and-code.md`, `docs/api.md`. Read those for detail; this is what matters most.

### 4.1 One customer message = three separate model calls

1. **Extraction** reads recent messages and fills the current step's `extraction_schema` variables.
2. **Routing** reads recent messages and the transitions' descriptions and picks a transition. It never sees the dialogue prompt.
3. **Dialogue** reads `system_prompt` + `role_message` + `task_message` + the full history and replies, or calls one of the current step's `tools`.

Consequences: a routing instruction inside a prompt does nothing. Variable conditions are checked in code with no model call. The model can only call the tools of the step it is in.

### 4.2 Step (node) types

| `node_type` | Does | Carries |
|---|---|---|
| `conversation` | Talks with the customer | `task_message`, `tools`, `extraction_schema`, `transitions` |
| `api_request` | Calls an API on entry, usually passes straight through | `pre_actions`, step-level `response_mapping`, `transitions` |
| `code` | Runs Python on entry, usually passes straight through | `pre_actions` with a `code_exec` function, `transitions` |
| `end_call` | Hangs up | `terminal` |

### 4.3 Variables

- One table per call. No scopes, never cleared; a later write overwrites.
- Sources: call variables, `test_variables`, extraction, `response_mapping`, code (`vars[...]`), system variables.
- Tool results are written automatically: `<tool>_response.data.<field>`, `<tool>_args.<field>`, `<tool>_success_count`, `<tool>_failure_count`. For `code` and `api_request` steps the keys are named after the **step**.
- `{{var}}` works in prompts, fixed lines, URLs and request bodies. An unresolved placeholder behaves differently by place: in a prompt the model sees the literal `{{var}}`; in a fixed spoken line the agent says it aloud; in an engine-run call a field that is exactly `"{{x}}"` is dropped; in a model-called tool a `{{x}}` default with no value becomes a parameter the model fills. So make sure an earlier step always sets every variable you reference.

### 4.4 Gotchas (each one breaks an agent without an error)

- Requests need a browser-like `User-Agent` or you get error 1010. `freya.py` sets it.
- An update is not live until it is **published**. `freya.save_workflow` publishes; a plain `PUT` does not. A run reports `agentVersionNumber`.
- No `null` anywhere in the workflow JSON.
- `tools` survive only on `conversation` steps, `pre_actions` only on `api_request` and `code` steps. Anything else is dropped silently. Read the workflow back after saving.
- `response_mapping` goes on the tool for `tools`, on the step for `pre_actions`. Paths start with `data.`.
- Booleans from results arrive as strings: test both `"true"` and `"True"`, or route on string flags.
- Every passthrough step needs a final `always` transition, or the call deadlocks.
- Code: read and write through `vars`, never let it raise (try/except with fallback values), and never put `{{` or `}}` anywhere in the code.
- Fixed tool values use `default`, never `const`. Each body field is a leaf under `body.properties` with its own `default`.
- A model-filled parameter must not share its name with a variable that is already set, or its value gets baked in and the model never sees it.
- Tool descriptions must be instructions with a trigger ("CALL it every time the customer gives an answer"), or the model answers in words and never calls the tool.
- The agent model often goes **silent after a tool result** or **ignores a negative result**. Fix: a post-hook that adds a `what_to_do_next` sentence to `result["data"]`, plus the prompt rule "after every tool result, speak to the customer or call the next tool".
- The model makes up product ids. Give ids in tool results, or fill them with code.
- The farewell comes from the end step's `terminal`, not from `on_enter`. `endedReason` is the terminal's `function.name`.
- `context_variables` did not survive a save over the API. Put values into prompts with `{{var}}`.
- Extraction `min_confidence` defaults to 0.95, which is too strict: set it on every variable.
- Built-in date extraction (`type: "date"`) has two traps here: it turns vague periods like "next week" into a concrete date (Brief A rule 21 wants you to ask once instead), and relative dates like "tomorrow" are most likely resolved against the real clock, not the `now` call variable. Safer: extract what the customer said as text and resolve it in code from `now`, or write a custom `extraction_prompt` that keeps all four `{{extractor.*}}` placeholders.
- Leave `agent_config` out of the workflow you send. The first `save_workflow` only creates the workflow; the model fix in `agent_config` happens on an update. A simulation runs anyway, but a chat turn may not start until you have saved a second time.
- The chat route may skip a first step that is a code step; a simulation runs it. Keep this in mind when you test with `tools/chat.py`.

### 4.5 Debugging tools

- `run_cases.py --out results/run.json` saves every call id.
- `freya.get_call(call_id)["messages"]` is the transcript with tool calls and `system` events.
- `route_evaluated` events list every condition, its result and the whole variable table: the fastest way to see why a route did or did not fire.
- `POST /api/v2/chat/message` runs one turn in seconds. `tools/chat.py` wraps it so you can play a practice customer.
- Ledger of a practice customer: `score.http("/v1/practice/ledger/" + customer_id)`.
- Calls ending `customer-ended-call` have two possible causes: the model was busy, or the agent went silent after a tool result. `run_cases.py` prints the median slowest turn: above 10 seconds, the model was busy, so rerun (`--rerun-if-slow 1` does this for you); below, the agent is at fault.

---

## 5. What the briefs ask for

Brief A has 47 rules and warns that most failures come from one skipped rule. The rules fall into families, and each family has a most reliable home.

| Family | Brief A examples | Most reliable home |
|---|---|---|
| Fixed sentences | Opening (digital assistant, recorded call); "You will receive a text message confirming this promise."; "I am sorry for your loss." | Fixed spoken lines or quoted text in prompts |
| Forbidden content | No "collections", "debt", "payment" or product before verification; nothing to relatives; no discounts, waivers or plans; never "how much can you pay?" | Prompt rules plus structure: debt facts only exist after verification |
| Who is on the line | Strict confirmation, asked at most twice; third party; wrong number; deceased; callback window 10:00–19:00 today or next business day | Conversation step with an extracted choice and routes |
| Identity | Two questions in order; 3 wrong answers in total; `day_month_swapped` hint; declines; unreadable answers not counted | Tool plus post-hook reading `all_verified`, `verified`, `wrong_answers_left`, `hint`, `ok` |
| Calendar | Business days, holidays, deadline per lateness band, "this/next <weekday>", vague period, weekend or holiday → next business day | **Code**: compute and hand the model finished facts |
| Amounts | Full amount first; floor offered once; below-floor offers; customer's own amount between floor and full accepted | Code computes floors; prompt applies them |
| Persuasion | Attempts per band (1 or 2); attempt 1 = last business day this week; attempt 2 = floor on the deadline | Code computes the offers; prompt uses them |
| Special situations | Hardship (comes first), already paid, dispute, restructuring, human, scam, robot question, unknown information, does not want to talk | Extracted intent plus routes; short prompt rules |
| Recording | Read-back and "Do you confirm?"; one promise per product; "recorded" only after `ok: true`; retry once, then `service_error` | Tool plus post-hook, maybe a guard |
| Closing | Exactly one `close_call`, last, outcome and reason from the table; goodbye first | End-of-call tool with outcome variables set during the call |
| Brief B | All products stated first; one "all today?" question; per-product band, deadline and attempts; one date clamped per product; one read-back for all; a note for every product without a promise; no notes on any transfer; closing outcome rule | Code for per-product facts and the closing outcome; prompt for the loop |

### Reference dates (now = Wednesday 14 October 2026, holiday Monday 26 October)

| Situation | Date |
|---|---|
| Next business day (callback, PUB-02) | Thursday 15 October |
| "This Friday" / attempt 1 (PUB-06, PUB-10) | Friday 16 October |
| Late-band deadline, 7th business day (PUB-04, PUB-13) | Friday 23 October |
| "Next Friday" said on a Wednesday (rule 22) | Friday 23 October |
| Monday 26 October is a holiday → next business day (PUB-07) | Tuesday 27 October |
| Early-band deadline, 12th business day (skips 26 October) | Monday 2 November |

### Clue for the hidden briefs

`run_cases.py` already knows identity answers that appear in neither brief: `postcode`, `birth_year`, `company_number`, `founded_year`. Expect other security questions, possibly a business customer. And `score.py` already accepts `no_contact` and `unreached` as "not reached" outcomes, so expect renamed outcomes too. The builder must read identity questions, outcome names and reasons from the brief and the tool API, never assume Brief A's.

---

## 6. Strategy

### 6.1 What the background paper teaches

The organizers named Shi et al., *τ^τ-bench (hyper-τ-bench): an environment for end-to-end, realistic agent construction* (Sierra and Princeton, arXiv:2609.04611, September 2026). It is not the older τ-bench of 2024. The extracted results, failure modes and section references are in `docs/sources.md`. A coding agent builds a customer-service agent from documents, then faces hidden simulated users: this hackathon at a larger scale.

- The best builder (Claude Code with Claude Opus 5) passed 23.9% of hidden conversations; expert-built agents passed 82.2%. Banking, with the most rules, scored 5.9%.
- Builders searched documents by keyword and missed rules.
- One build passed all 10 of its own tests and scored 59.7%: its tests never reached the policy branches the hidden set tested. Some builders weakened failing tests until they passed.
- Builders rewrote the starter code without running it first.
- 92% built a single prompt-and-tools loop. A one-line hint, "route by intent, review tool calls", raised one score from 31% to 67%.
- Builds that asked the client four or more questions scored about three times higher than builds that asked none (0.50 vs 0.16).
- An agent that retried a write without checking told a customer a booking failed when it had gone through.

### 6.2 Principles

1. **Run what exists first.** The example builder passed 10 of 10 Brief A customers in one run. Measure it with `--reps 3` before you change anything.
2. **Every rule must land somewhere.** Number all rules; map each to code, a hook, a route, a fixed line or a prompt. An unmapped rule is a build error.
3. **Put each rule in its most reliable home** (table in section 5).
4. **Route by intent, review tool calls.** Separate steps with routes on extracted choices; hooks around every tool call.
5. **Keep prompts short.** The agent model is sometimes slow, and long silences make customers hang up.
6. **Consistency over luck.** Fixed code stages and low-temperature builder calls, so the same brief gives the same agent on a rerun.

### 6.3 The builder pipeline

1. **Normalize** (Claude). Read every brief file completely. Write `policy.json` in a fixed schema. Later memos override earlier text. List any remaining ambiguity in the trace.
2. **Render** (Python). Fill a proven workflow template from `policy.json`. Date code and hooks receive the policy values as literals.
3. **Adapt** (Claude). Go through the brief rule by rule against the workflow; add prompt text for anything the template does not cover.
4. **Validate.** Dry run, save in the brief's slot, read back, check that the expected steps and tools survived.
5. **Self-test** if time and test customers allow: one short run, one round of fixes.
6. **Export** and finish the trace.

**Lighter fallback:** keep the example builder (Claude writes the workflow) and give its skill the date code, hook snippets, the gotchas and the rule-mapping step. Two gaps to close if you do: its trace has no end time and no workflow id, agent id or step and tool counts, and nothing stops it at 30 minutes (only `max_turns=150`). Wrap it to add both.

**Keep practice knowledge out of hidden builds.** The example builder runs Claude with the kit folder as its working folder and loads project settings, so it can read `CLAUDE.md`, `PLAYBOOK.md`, Brief A and the public test set. On a hidden brief, Brief A's values could leak into the agent. Give your builder its own working folder that contains only its skill, the brief(s) it was given and the tool API file.

### 6.4 `policy.json`: a first sketch

```json
{
  "bank_name": "Freya Bank",
  "language": "English",
  "opening_sentence": "...",
  "confirmation": {"accepted": ["yes", "that's me", "speaking", "own name"], "max_asks": 2},
  "forbidden_before_verification": ["collections", "debt", "payment", "product names"],
  "callback": {"days": ["today", "next_business_day"], "from": "10:00", "to": "19:00"},
  "identity": {
    "questions": [{"field": "date_of_birth", "format": "YYYY-MM-DD"}, {"field": "phone_last4", "format": "4 digits"}],
    "max_wrong_total": 3,
    "on_fail": "tell the customer to use the mobile app or a branch"
  },
  "calendar": {"business_weekdays": [0, 1, 2, 3, 4], "holidays": ["2026-10-26", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01"]},
  "bands": [
    {"name": "early", "days_late_min": 1, "days_late_max": 7, "deadline_business_days": 12, "attempts": 1},
    {"name": "late", "days_late_min": 8, "days_late_max": 45, "deadline_business_days": 7, "attempts": 2}
  ],
  "floor_field": {"credit_card": "minimum_payment", "personal_loan": "instalment_amount", "car_loan": "instalment_amount"},
  "product_words": {"credit_card": "credit card ending {card_last4}", "personal_loan": "personal loan", "car_loan": "car loan"},
  "sentences": {"after_promise": "You will receive a text message confirming this promise."},
  "queues": {"restructuring": "restructuring", "human": "general", "support": "support"},
  "outcomes": [{"outcome": "promise", "reason": "", "when": "at least one promise recorded"}],
  "rules": [{"id": "A1", "text": "...", "home": "fixed_line | code | hook | route | prompt"}]
}
```

The values above are Brief A's, as an example of the shape only. The builder must fill every value from the brief it is given.

### 6.5 Workflow template (proposal, verify on the platform)

| Step | Type | Job |
|---|---|---|
| `opening` | conversation | Opening line; confirm the right person; answer robot and scam questions; route on an extracted choice: customer, someone else, wrong number, deceased, unclear |
| `third_party` | conversation | Say nothing about the account; ask when the customer can be reached; `schedule_callback` inside the window |
| `identity` | conversation | `verify_identity` with a post-hook; routes on all verified, no wrong answers left, declined |
| `account` | api_request, passthrough | `get_account`; post-hook computes per-product facts: ids, words, band, deadline, floor, offers, plus the calendar facts |
| `negotiate` | conversation | State the debt; the promise flow; `create_promise`, `add_note`, `transfer_to_agent`, each with a hook |
| `set_outcome_*` | code, passthrough | Sets `outcome` and `reason` from the call's state (for Brief B, from promises and notes recorded) |
| `end_*` | end_call | One per outcome family; farewell in the terminal |
| `close_call` | workflow-level tool, `alwaysRunsAt: end_of_call` | Sends `outcome` and `reason` from the variables; the pre-hook drops `reason` for promise and paid (as in `examples/base-agent.json`) |

Why `account` is its own step: `get_account` can then only run after the identity route fired, which the ledger check requires.

### 6.6 Date engine (code)

Computes from `now` and the policy: today and its weekday; business days (weekdays minus holidays) for the next ~40 days with weekday names; the deadline per band; the last business day of this week (or of next week if today is that day) for attempt 1; a "this <weekday>" and "next <weekday>" table; the next business day; the callback window. It writes a short text block into a variable for the prompts and per-product variables for routes and hooks.

Test it locally, with no Freya, against the reference dates in section 5. Then test other values of `now`: a Friday, a Monday, the day before a holiday.

### 6.7 Hooks (proposal)

- **`verify_identity` post-hook:** turn `all_verified`, `verified`, `wrong_answers_left`, `hint` and `ok` into one `what_to_do_next` sentence: next question; same question again; ask for the month as a word; check failed, tell them about the app or a branch.
- **`get_account` post-hook:** drop headers; add a compact product summary with ids, words, amounts, band, deadline, floor and the two offers.
- **`create_promise`:** post-hook says "recorded, now say the text-message sentence" only on `ok: true`; on failure "not recorded, try once more", and after the second failure "say you could not record it". Count failures yourself in `vars`, from `data.ok` and `status_code`: the docs don't say whether an `ok: false` reply with status 200 raises `create_promise_failure_count`. Worth a 5-minute test: `maxRetries: 1`, because the API says a 500 recorded nothing, so a retry is safe.
- **Guard idea (test first):** a `create_promise` pre-hook that checks the date and amount against the computed limits, so a promise that breaks the rules is never written to the ledger.

---

## 7. Testing

### 7.1 Commands

```bash
python3 tools/run_cases.py <agent_id> --brief A --reps 3 --out results/a.json
python3 tools/run_cases.py <agent_id> --brief B
python3 tools/run_cases.py <agent_id> --brief A --style in_words     # also: pieces, corrects, talkative, asks_back
python3 tools/run_cases.py <agent_id> --only PUB-03,PUB-10           # a few customers, faster
```

`results/log.jsonl` keeps one line per run: your score history.

### 7.2 Cover what the public set misses

The hidden set has 30 customers per brief; the public set has 13 in total. Two ways to widen coverage with the kit's own tools:

- **New scenarios for existing customers.** `run_cases.py` gets a test customer from the practice endpoint by case id; the customer's behaviour comes from the `script`, and the result is checked against `expected`. So in a copy of the test set (for example `tests/extra-cases.json`), add cases that reuse an existing customer: copy `brief`, `level`, `variables`, `identity` and `products` from it; give a new `id`, `title`, `family`, `script`, `expected` and `checks`; add `"session_case": "PUB-01"`. For someone-else-answers scenarios set `"family": "Third party"` or `"third_party": true`, or the simulated caller gets the security answers. In `run_cases.py`, request the session with `c.get("session_case", c["id"])`, then run with `--cases tests/extra-cases.json`. Reuse PUB-10's customer when you want the first `create_promise` to fail.
- **Other calendar days.** Change `now` in the session variables before the simulation and recompute the expected dates. The bank mock does not check the rules, so it does not care what day it is.

Situations worth adding for Brief A: wrong number · deceased · only "hello" or "who is this" twice · relative offers times outside the window twice · declines the security questions twice · asks "what is this about?" instead of answering · day and month swapped · asks for a human and insists · asks "is this a scam?" then pays · disputes the debt · offers less than the floor, then accepts it · offers an amount between floor and full · changes the date at the read-back · hardship and accepts the support team · hardship but names a date · flat refusals in the early band (1 attempt) and late band (2 attempts) · weekend date · "next Friday" said on a Friday. For Brief B: restructuring after one promise was recorded · dispute on one product, promise on another · all products already paid.

**Write each expected outcome from the brief before you see what the agent does. Never change an expectation to match the agent.**

### 7.3 Test generalization without Freya

Have Claude write variant briefs: (1) Brief A with other holidays, bands, deadlines, floors, identity questions (postcode, birth year) and outcome names; (2) Brief A as raw material: an email, a policy extract, a memo that overrides two values, a code list. Write the expected `policy.json` for each by hand and check that the normalize stage reproduces it. Seconds per check, no simulation needed.

### 7.4 Read results like a statistician

- 3 of 3 is harsh: 90% per run gives 73% of customers passing all three; 80% gives 51%.
- With 13 cases one customer is 7.7 points. Most differences between two versions are noise. Compare versions on the same customers, look at the cases where they disagree, and use `--reps`.
- Each run takes 3 to 11 minutes and blocks the workspace. Decide which runs are worth it.

---

## 8. Working in VS Code with Claude Code

- `CLAUDE.md` at the repo root holds the hard rules, commands and code style for your Claude Code session. It is for you, not for the builder: give the builder its own working folder (section 6.3) so it never reads `CLAUDE.md`, this playbook or Brief A during a hidden run.
- Loop per component: `/clear` → plan mode (`Shift+Tab`) → `ultrathink` for design decisions → read and edit the plan → implement → test → reviewer subagent → commit.
- Never let Claude hard-code anything from a brief, and never let it edit a test's expected outcome.
- Headless failure analysis: run `claude -p` over failed transcripts to classify the root cause of each failure.

---

## 9. First hour: explore Freya

1. **Set up.** `cp env.example env.sh`, add your Freya key and a team key of 16+ characters, `source env.sh`. In the dashboard, count your workflows (limit 200) and note the credit balance. At the start on 10 October the workspace held one workflow (the pre-loaded base agent) and $250 of credits. The kit does not say what a simulation costs: read the balance again after the first 10-customer run and budget the test plan from that number. `FREYA_WORKSPACE_ID` in `env.sh` saves `freya.py` a lookup; the id is in the dashboard URL.
2. **Put the example agent on Freya.** Run this from the kit folder, **twice**: the first run creates the workflow, the second sets the event model and publishes, which a chat turn needs.
   `python3 -c "import freya,json; print(freya.save_workflow('base', json.load(open('examples/base-agent.json'))))"`
   It prints the `workflow_id` and `agent_id`; the slot is stored in `.freya-agents.json` in the folder you ran it from. Open the workflow in the dashboard and compare the screen with the JSON.
3. **Talk to it.** `python3 tools/chat.py base PUB-01`: you play Daniel Reyes. Confirm, give the date of birth in words, give wrong phone digits once, ask "is this a robot?". At the end the script prints the tool calls and the bank's ledger.
4. **Read the events of that call.** Look at `route_evaluated`, `function_call_start` and `function_call_complete`, and the variable table.
5. **Run the Brief A customers on it.** `python3 tools/run_cases.py <agent_id> --brief A`. Expect very few passes (the README reports 2 of 13). Read why the others fail.
6. **Run the example builder on Brief A.** Time it. Read its trace in `traces/` and the workflow it created. Test its agent with `--reps 3`, then `--brief B` (build with both briefs), then one `--style`.

Write down what surprised you, what failed and how long each step took. That list drives tomorrow.

---

## 10. Timeline

### Tonight

| Time | What |
|---|---|
| 21:30–22:30 | Explore Freya (section 9, steps 1–5) |
| 22:30–23:15 | Baseline: example builder, `--reps 3`, Brief B, one style (step 6). Read failures while it runs |
| 23:15–00:30 | `builder/build.py` skeleton: command shape, fixed slots, trace. Date engine with local tests. Commit. Sleep |

### Sunday

| Time | What |
|---|---|
| Until 13:00 | Hooks; normalize and render (or the skill upgrade); Brief B |
| 13:00–16:00 | Extra test customers and calendar days; variant briefs; build time; check that two reruns give similar agents |
| 16:00–18:00 | Freeze. A fresh clone runs the exact command. README, trace check, export path |
| 18:00–20:00 | Rest and dinner |
| 20:00 | Hidden briefs open. Build hidden-1, then hidden-2, one after the other (one simulation at a time). Each run exports right after it finishes |
| About 21:15 | Optional second run of each, in its own slot; keep the better one only if they are close. Commit |
| By 22:30 | Submit the form. Deadline 23:00 |

### Hidden-brief checklist (Sunday 20:00)

- [ ] Save the briefs and API files under `briefs/` exactly as received
- [ ] Run the exact command, e.g. `python3 builder/build.py briefs/hidden-1.md briefs/hidden-1.openapi.json 2>&1 | tee traces/hidden-1.log`
- [ ] Check the trace has every required part; remove keys
- [ ] Check that each run exported its workflow to a file named for that run; commit; note the commit hash
- [ ] Submit the form: team, repo, commit, run_command, workflows, traces

---

## 11. Questions for the organizers

- Do the hidden briefs come with practice customers, or can practice sessions be created for them? If not, how should a builder test itself on a hidden brief?
- Answered: the workflow limit is 200 on both the hackathon page and the README.
- Will each hidden brief be one file, or several files for the raw material?

---

## 12. Pre-submission checklist

- [ ] A fresh clone, setup and the one command run end to end on a brief the builder has never seen
- [ ] Secrets only from environment variables; no keys in the repo or traces
- [ ] Dependencies and builder model names pinned; the exact commit is in the submission
- [ ] The builder stops itself before 30 minutes and always saves a valid workflow
- [ ] One slot per brief and run, updated in place; the workspace limit is 200
- [ ] The builder runs in its own working folder and cannot read `CLAUDE.md`, this playbook, Brief A or the public test set
- [ ] Nothing from any brief hard-coded in code, prompts or templates
- [ ] Works with: other identity questions, other calendars and bands, raw-material briefs, one to three products
- [ ] Every generated agent: no debt talk before verification, read-back before every write, "recorded" only after `ok: true`, exactly one `close_call`, goodbye before it
- [ ] Measured with `--reps 3` and at least one `--style`; expectations written from the brief
- [ ] The trace has start/end time, every model call, Freya ids and counts, every self-test and result
- [ ] README: setup, environment variables, the run command, expected time and cost

---

## Sources

- Kit v3: `README.md`, `docs/workflow-format.md`, `docs/tools-and-code.md`, `docs/api.md`, `freya.py`, `tools/run_cases.py`, `tools/score.py`, `briefs/brief-a.md`, `briefs/brief-b.md`, `tools/openapi.json`, `public-test-set.json`, `examples/`
- Hackathon page: https://www.freyavoice.ai/hackathon
- Organizers' email of 10 October (timeline, tools allowed, background paper)
- Extracts from the hackathon page and the paper, with numbers and section references: `docs/sources.md`
- Shi, Dhandhania, Narasimhan, Barres, *τ^τ-bench: an environment for end-to-end, realistic agent construction*, arXiv:2609.04611 (https://arxiv.org/abs/2609.04611)
