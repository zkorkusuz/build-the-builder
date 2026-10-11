# Runbook for the hidden briefs (Sunday 20:00 to 23:00 Istanbul = 17:00 to 20:00 UTC)

Rehearsed on Sunday afternoon: a fresh clone, the one command, the helper, and two platform outages.
Times are Istanbul. The briefs open at 20:00, the form closes at 23:00; the target is a submission by 21:30.

## Before 20:00
- Code committed and pushed; `git status` clean (the trace's `builder:` line names the commit and says whether the tree was clean).
- `.venv/bin/python -m unittest discover -s tests -q` passes.
- In the terminal you will use: `source env` and `source .venv/bin/activate` (so that `python3` is 3.14, the literal run command of the form).
- No simulation running in the workspace (the helper warns; cancel a stuck one with
  `python3 -c "import freya; print(freya.cancel_simulation('<id>'))"`). The platform watcher is running.
- Read the credit balance. A build costs about $0.60 of Claude credits and nothing on Freya.

## 20:00: save, build, check
1. Save each brief exactly as received: `briefs/hidden-1.md` with `briefs/hidden-1.openapi.json`, `briefs/hidden-2.md` with
   `briefs/hidden-2.openapi.json`. Each hidden brief is one Markdown file (organizers' FAQ). Nothing from them goes anywhere else:
   not into code, prompts, tests, the tracker or memory.
2. One command runs both builds in turn, checks each and prints the form:
   `python3 tools/hidden.py briefs/hidden-1.md briefs/hidden-1.openapi.json briefs/hidden-2.md briefs/hidden-2.openapi.json --team <name>`
   It waits for the platform first, builds hidden-1 (about 2 minutes), checks it, then hidden-2. Everything a build prints lands in
   `traces/hidden-N.log`; the builder also writes `traces/hidden-N-<start>.log` and `.policy.json`; the export is `hidden-N.workflow.json`.
   Without the helper, the literal command is `python3 builder/build.py briefs/hidden-1.md briefs/hidden-1.openapi.json 2>&1 | tee traces/hidden-1.log`.
3. Read the trace while it runs: the `policy:` lines (identity questions in order, bands and deadlines, holidays, callback window, outcomes),
   every `ambiguity:` line, the `fields:` line, the `dry run:` line and the `self-test: chat probe` line (the agent's opening with the made-up
   customer's name). A reading you disagree with is noted for the write-up, never edited: the briefs and the builder stay as they are.
4. The helper's `check:` lines. `clean` means: every required trace line present, export read back from the platform with the trace's
   workflow id and counts, no fallback, no key. `trace (kept): ...` notes are informational (a repair call, a skipped stage): the run is kept.

## When a build must be repeated, and how to find the cause
- The helper builds a brief once more by itself after a crash (no result line) or a fallback (`FAILED`, `bare template`, `rejected`,
  `out of time`), and prints the cause lines first. The slot is updated in place, so the last run's export and trace are the submission.
- If the second build fails the same way, stop and look: `work/<slot>/policy.json` is what the renderer got; the trace's last lines say
  which stage failed. The one allowed change after 20:00 is a crash fix that generalizes (a table format or a field type the code did not
  expect), never a value, a name, a date or a reading from the brief. Add a unit test for the shape that crashed, commit, run the helper again
  for that brief only. If the crash cannot be fixed in 20 minutes, submit the bare-template agent of the last run with its trace.
- Never rerun to pick the nicer of two readings: the organizers rebuild the top entries and drop a submission that scores clearly above their rebuild.
- The platform away: the helper waits up to 20 minutes before a build; inside a build the save retries until ten minutes before the cap.
  Do not start a second build meanwhile. `export: written from the saved workflow` is a fallback to note, not to rerun.
- Never pipe a run through `head`; never kill a runner while its simulation runs; never start a simulation while one runs.

## Commit and submit (target 21:30, hard stop 22:30)
1. `python3 tools/hidden.py ... --commit` commits the briefs, API files, logs, traces, policies and exports (or `git add` those files and
   commit by hand). `git push`. Note the hash: it must be the commit that holds the files, on code identical to what ran (clean tree at 20:00).
2. Make the repository public.
3. Send the form from `work/form.json` (the text in `docs/submission.md`): team, repo, commit, the literal run command, the two export paths,
   the two console logs.
4. After sending, touch nothing: no edit to an export, no rebuild into the same slot.

## Do not
- Do not change builder code, templates or prompts after 20:00 except a generalizing crash fix as above.
- Do not run a simulation of a hidden agent: no practice customers exist for it, the organizers score on their own platform.
- Do not write test customers from the hidden briefs.
