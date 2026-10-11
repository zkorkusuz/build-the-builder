# Runbook for the hidden briefs (Sunday 20:00 to 22:30 Istanbul)

Everything here was rehearsed on Sunday afternoon: a fresh clone, the one command, and two platform outages.
Times are Istanbul. The briefs open at 20:00, the form closes at 23:00; the target is a submission by 22:30.

## Before 20:00
- `git status` clean on the submission commit; `.venv/bin/python -m unittest discover -s tests -q` passes.
- `source env` in the terminal you will use. The watcher (`scratchpad/platform_watch.py`) is running or restarted.
- The dashboard shows no simulation running. If one is stuck, cancel it:
  `.venv/bin/python -c "import freya; print(freya.cancel_simulation('<id>'))"`.
- Read the credit balance; a build costs about $0.60 of Claude credits and nothing on Freya.

## 20:00: build hidden brief 1, then hidden brief 2
1. Save the files exactly as received under `briefs/`: `briefs/hidden-1.md` (several files if the brief comes as several,
   for example `hidden-1-email.md`, `hidden-1-memo.md`, `hidden-1-codes.md`) and `briefs/hidden-1.openapi.json`.
   The slot name is the brief file names joined with `_`, so keep them short.
2. Run the one command, brief files first and the API file last:
   `.venv/bin/python builder/build.py briefs/hidden-1.md briefs/hidden-1.openapi.json 2>&1 | tee traces/hidden-1.console.log`
3. Expect about 2 minutes. The build prints one JSON line at the end with `workflow_id`, `agent_id`, the export file
   (`<slot>.workflow.json`) and the trace (`traces/<slot>-<start>.log`).
4. Read two things in the trace while it runs: every `policy: ambiguity:` line (how the model resolved what the brief left
   open) and the `fields:` line (which tool fields it mapped to other names). If an ambiguity resolution contradicts the brief,
   fix the brief text? No: nothing in the brief may be edited. Note it for the write-up and move on.
5. Build hidden brief 2 the same way, after the first has printed its JSON line. One build at a time.

## If something goes wrong
- `save: failed ... trying again in 20 s`: the platform is away. The build keeps trying until ten minutes before its cap and
  then raises. Wait for it; do not start a second build. If it raises, run the same command again: the slot is updated in place.
- `render: FAILED on this policy`: the bare template was saved so that a workflow exists. Look at `work/<slot>/policy.json`,
  then run the command again; if it fails the same way, that is the one case where a code fix after 20:00 is allowed
  (a crash on an unexpected table format, per the hackathon rules). Keep the fix to the crash.
- `export: written from the saved workflow`: fine, the file holds the workflow as saved.
- The dry run failed with a 4xx: the build saves the bare template and says so. Run the command again after checking the policy.
- Never pipe a run through `head`; never kill a runner while its simulation runs; never start a simulation while one runs.

## Commit and submit (by 22:30)
1. `git add -A && git commit -m "Hidden briefs built" && git push` (traces and exports are tracked; `env`, `work/`, `results/` are not).
2. Note the commit hash. Make the repository public.
3. The form: team, repository, commit, the run command above, the two `workflow_id`s and agent ids from the JSON lines,
   the two export files and the two traces.
4. After submitting, touch nothing.

## Do not
- Do not change builder code, templates or prompts after 20:00 except for a crash fix as above.
- Do not run a simulation of a hidden agent unless there is time to spare and the workspace is free; the organizers score
  on their own platform, and our runs do not count.
