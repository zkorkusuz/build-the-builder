# Sources: what the hackathon page and the background paper say

Extracted on 10 October 2026 from the pages linked below, for the developer's Claude Code session and the reviewer
agent. The builder does not need this file: it reads only its skill, the brief(s) and the tool API file.

## 1. Hackathon page

Source: https://www.freyavoice.ai/hackathon. "Build the Builder", Freya × Y Combinator, 10 and 11 October 2026, online,
solo or teams of two. Domain: debt collection. Conversations are text, in English. 13 practice cases, 60 hidden cases.

### Schedule (the page is in UTC; Istanbul is UTC+3)

| Step | UTC | Istanbul |
|---|---|---|
| Kit and Freya keys released | Sat 10:00 | Sat 13:00 |
| Two hidden briefs open, each with its own tool API file | Sun 17:00 | Sun 20:00 |
| Submission closes | Sun 20:00 | Sun 23:00 |

The three hours after the briefs open are for running the builder and fixing bugs, not for tuning it to the new briefs.

### Scoring

- A customer passes only if all three checks pass, with no partial credit. Outcome: the bank's ledger is correct (right
  product, date, amount, recorded once), read from the mock bank records. Policy: the call stayed within the brief,
  judged from the transcript by a judge model. Honesty: the agent did not claim a recording that failed.
- A correct refusal (for example a recorded dispute with no promise) counts as a pass.
- 2 hidden briefs × 30 customers. Each case runs 3 times and passes only if all 3 runs pass. Score = cases passed / 60.
- Tie-breakers: total promised amount on passing cases, then shorter total build time from the traces, then earlier
  submission.

### Limits and rules

| Item | The page says |
|---|---|
| Builder run time | 30 minutes per brief, including any self-tests |
| Workflows per workspace | 200. Update a workflow in place rather than creating a new one per run |
| Practice simulations | One at a time per workspace. Ten cases take about 3 to 11 minutes |
| Freya keys | One per team |
| Models | Any model or coding agent for the builder, paid by the team. The phone agent model is fixed in `freya.py` |
| Tools the phone agent may call | Only the seven kit tools |
| After the hidden briefs open | Bug fixes only. Nothing from a hidden brief (rule, value, name) may be written into the builder. Fixing a crash on an unexpected table format is allowed |
| Entry | A hand-built phone agent alone is not valid. It must come from the submitted builder |
| Platform | Do not probe or load-test it |
| Data | Synthetic only |

### Submission

- One phone agent per hidden brief, exported with `freya.export_workflow`, committed to the repository, not edited
  after the run.
- One plain-text trace per hidden brief, without API keys: start and end time, model calls, created workflow and agent
  ids, any self-tests. Coding-agent session logs are optional.
- The form goes to the address in the kit email before 20:00 UTC: team name, repo URL, commit, run command
  (`python3 builder/build.py {brief_path} {tool_api_path}`), workflow file paths, trace paths.

### Verification

The top ten builders are cloned, rerun on the same briefs and compared with their traces. A reviewer agent checks each
trace against the submitted code and phone agent. Entries whose rerun scores clearly lower are removed.

### Prizes and support

First place: a YC interview. Second: AirPods. Top three: a final interview with Freya. $3,000 in Freya credits.
Support runs through the login email.

### Where the page differs from the kit or the playbook

- Workflow limit: the page and the README both say 200. The playbook's earlier figure of 10 was wrong and is corrected.
- The page names no external reading. The background paper came from the organizers' email.

## 2. Background paper: τ^τ-bench

Quan Shi, Keshav Dhandhania, Karthik Narasimhan, Victor Barres (Sierra and Princeton). *τ^τ-Bench: An Environment for
End-To-End, Realistic Agent Construction.* arXiv:2609.04611, submitted 4 September 2026, 41 pages.
Abstract: https://arxiv.org/abs/2609.04611 · Full text: https://arxiv.org/html/2609.04611

It is not the 2024 τ-bench (Yao et al., arXiv:2406.12045), which scores an agent that operates. This paper scores a
developer agent that builds an agent, which is this hackathon's task.

### What it measures

A developer agent receives business records, a client that holds the requirements, a production API, an inherited
codebase, and limits on serving cost and models. It must deliver a complete customer-service agent. The agent is then
deployed against held-out simulated users, each with a hidden goal and a ground-truth outcome. A task passes when the
final database state and the information given to the user match the annotated outcome; messaging is graded by
rubric-driven judges (§3.1, Appendix K). 53 release tasks in four domains, one construction trial each; a second set of
53 tasks is private (§4, §7).

### Results (Table 2)

| Builder | Overall | Airline | Retail | Telecom | Banking |
|---|---|---|---|---|---|
| Claude Code + Claude Opus 5 | 23.9% | 55.9 | 72.8 | 48.2 | 5.9 |
| Codex + GPT-5.6-sol | 22.0% | 49.8 | 59.2 | 32.9 | 9.0 |
| Expert reference ceiling | 82.2% | 82.3 | 84.0 | 93.8 | 79.8 |

Banking is the hardest domain, with 2,969 atomic facts against 85 to 155 in the other domains (§5, Appendix B). Our
briefs are a banking task.

### Failure modes of builder agents, and where the playbook answers them

| Failure (section) | What the paper measured | Playbook answer |
|---|---|---|
| Keyword search instead of reading (§6) | Builders opened fewer than 80 of about 1,700 files and ran 22 to 53 corpus-wide searches | The normalize stage reads every brief file completely; every numbered rule gets a home (§6.2) |
| Not asking the client (§5, §6, Figure 4) | At most four questions, each triggered by a conflict; 0.3% of tool calls. Builds that asked four or more averaged 0.50, builds that asked none 0.16 | No client exists at hackathon time: list every ambiguity in the trace and resolve it with a stated assumption |
| Rewriting the starter code unrun (§6) | Every builder read the starter code, none ran it before rewriting | Measure the example builder with `--reps 3` before changing anything (§6.2) |
| Missing quiet API defects (§6) | Loud failures were caught; silent ones, such as results continuing behind a cursor, were missed | Read `route_evaluated` events and the variable table, not only the transcript (§4.5) |
| Retry and honesty bugs (§6) | Agents told a customer a booking "did not go through" when it had committed; another said a pending update "should be confirmed shortly" without checking | "Recorded" only after `ok: true`; a 500 from the bank mock recorded nothing, so one retry is safe; count failures in a hook (§6.7) |
| Weakening tests (§6) | Six runs weakened failing assertions; one invented a rule the records did not contain; one faked a failing endpoint in its own mock | Expectations are written from the brief before the run and never changed to match the agent (§7.2) |
| Self-tests pass, hidden tests fail (Figure 8, Appendix C) | All ten self-written probes passed, yet about two-fifths of the held-out suite failed on policy branches the probes never reached | Extra cases for the rare branches and for other calendar days (§7.2) |
| Single prompt-and-tools loop (§5) | 92% of builds; only 15 of 36 possible architecture combinations appeared. A one-line hint, "route by intent, review tool calls", raised a telecom score from 31% to 67% | Steps with routes on extracted choices and a hook around every tool call (§6.2, §6.5) |
| No deterministic guards (§5) | 71% of Codex and 57% of Claude Code builds gated output behind deterministic policy guards; 14 to 15% of Kimi Code and OpenCode builds did | Dates, floors and offers computed in code; a pre-hook guard on `create_promise` (§6.6, §6.7) |
| Budget misuse (§5, §6) | Builders used about half their serving budget; 21 overshot it and the penalty erased ten positive scores; twelve submitted with half or more of the build clock unused | Use the 30 minutes: one self-test and one round of fixes when time allows (§6.3) |

### What the expert references did differently (§4, §5)

- A much wider variety of architectures than any builder model.
- 0.96× of the serving budget used, against 0.45× to 0.72× for builders.
- Built by an expert working with a model from ground truth: an oracle, not average human performance.

### Judging details worth knowing (simulated-user instructions, Appendix K)

- The simulated user reveals information only when asked, and ends the conversation only after the agent has finished
  every required action. The customer's consent alone does not complete a task.
- A spoken-register variant spells identifiers letter by letter and reads digits one at a time. This matches the
  `pieces` and `in_words` styles of `run_cases.py`.
- The one judge rubric printed in the paper fails an agent when two customer-facing responses open with the same reusable
  template, for example repeated apology or confirmation frames. Whether the hackathon's judge checks this is not
  known; varying the wording of repeated read-backs and refusals costs nothing.

## 3. Platform documentation

- Kit docs: `docs/workflow-format.md`, `docs/tools-and-code.md`, `docs/api.md`. The workflow JSON is documented only
  there.
- Freya docs: https://docs.freyavoice.ai for personas, simulations and calls.
