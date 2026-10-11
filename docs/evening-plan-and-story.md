# Sunday evening: plan to 20:00, the hidden briefs, and the story to tell

## State at 16:05
- Code: commit 5f24cee, pushed to the private repo. 53 tests. Brief A version 54 is the measured build; version 56 is
  rebuilt automatically after run 37 on the final code (the only runtime difference: ordinal day words now parse).
- Running: run 37 (21 cases x3 on v54; rep 1 21/21, rep 2 19/21 with two platform hang-ups, rep 3 in progress), then
  the Brief B run on our mock, then the talkative and asks-back styles once each. The watcher and alerts stay on.
- Not ours to fix: the platform's model latency (customers hang up on long silences), judge variance (~3% of calls),
  the sandbox fault (~1% of calls), persona truncation.

## 16:15 to 20:00
1. 16:15 run 37 result: review every failure with `tools/review_run.py results/run37-reps3.json`. A rule gap gets a
   unit test, a fix, and a targeted `--only` rerun x3. A platform or judge loss gets a note in the tracker.
2. 16:20 to 17:15 (automatic): v56 rebuild, Brief B on the mock, two styles. Read each result as it lands.
3. 17:15 to 17:45: triage of B and the styles. Only crashes and rule gaps are fixed; everything else is written down.
4. 17:45 to 18:30 freeze: final commit and push; README checked (setup, the command, time and cost); traces and exports
   committed; `docs/submission.md` with the form text (team, repo, commit, run command); tracker and memory final.
5. 18:30 to 19:45: no changes. Eat. Keep the watcher running.
6. 19:45 pre-flight: dashboard shows no running simulation; `source env`; `git status` clean; credits noted.
7. 20:00 to 22:00: `docs/runbook-2000.md`, one brief at a time. Read the trace's ambiguity lines and the fields line in
   the first two minutes of each build. Commit, push, make the repo public, submit by 22:00 to keep a margin.

Decision rules after 20:00: no code change except a crash fix; never edit a hidden brief; if the API file has an
unusual shape, trust the `fields:` trace line and the dry run before anything else; one build at a time.

## The story, if it comes to a presentation
Six parts, one figure each where it fits (docs/figures):
1. Framing. The score is pass-all-three on hidden customers, so consistency beats peak: a 90% agent gives 73% of
   customers, an 80% one gives 51%. The paper's best builder reached 23.9%, banking 5.9%.
2. The principle. Every failure was traced to a decision the model made that code could make instead, and the decision
   moved: counting asks, converting dates, joining split answers, naming the end reason, the outcome, the close.
   Sixteen moves in one day (figure 4). The model only speaks.
3. The pipeline. Normalize reads every line of the brief into one policy; render puts dates, counters and guards into
   code steps and hooks and the flow into routes; adapt adds prompt text only for what structure cannot carry; lint and
   dry run; publish; export. About 110 s and $0.60 per brief (figure 1).
4. Evidence. From 17 of 21 to 21 of 21 three of three, and what each step fixed (figure 2). Robustness: five speaking
   styles, other calendar days, two other banks built from an email, a memo and a code list and from a clean spec,
   a tool API with eight renamed fields and a prefixed path (figure 3).
5. Errors, both kinds. In the conversation: a blocked call never reaches the bank, "recorded" is said only after the
   bank says ok, one promise per product, a bank rejection corrected at most twice, a failed service never claimed.
   On the platform: retries in one place, a save loop bounded by the budget, an export written from the saved
   workflow, polls that outlive an outage, a cancel for stuck simulations, a watcher, and a triage that keeps
   platform losses out of the agent's score.
6. Method and limits. Expectations written from the brief before any run and never changed; the review loop prints
   every decision with its maker; a reviewer after every change; an independent QA review; eighteen papers read for
   what transfers. Limits: multi-product negotiation is prompt-only, the second attempt's wording comes from the policy
   but its logic is still the floor-or-full choice, consent is a model judgement, a hang-up leaves the ledger open.

Three numbers to say out loud: 21 of 21 three of three on the practice set; 16 decisions moved out of the model;
about 1% sandbox and 3% judge noise as the floor nobody's code can remove.
