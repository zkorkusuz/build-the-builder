# Runbook for the final (Sunday 11 October 2026, 20:00 to 23:00 Istanbul)

The final is one case: Freya Bank's card statement-debt line, in Turkish. The input is one zip with a folder of documents
(BRIEF.md first, README.md says what each document is) and the service contract; the bank mock is ours, on Cloudflare
Workers, and must stay up until results are out. One `submission.json` goes by email before 23:00; aim for 22:00.
Times are Istanbul. This is the only runbook; `tools/hidden.py` is the helper that runs the one command, checks the run and
prints the form.

## Before 20:00
- In the terminal you will use: `source env` and `source .venv/bin/activate` (so `python3` is the venv's interpreter, the
  literal run command of the form). `.venv/bin/python -m unittest discover -s tests -q` passes. `git status` clean and pushed.
- The mock answers: `python3 mock/check.py https://bank-mock.bank-mock.workers.dev PUB-01` prints one call per tool and a
  ledger with one promise, note, callback and transfer. `cd mock && npx wrangler whoami` shows the account.
- No simulation running (`python3 -c "import freya; print(freya.cancel_simulation('<id>'))"` cancels a stuck one). A build
  starts none; it costs about $0.60 of Claude credits and nothing on Freya.

## 20:00 to 21:00: read, reshape the mock, build
1. Unzip into `briefs/final/` (keep the folder name the zip gives; it becomes the slot). Read `BRIEF.md`, `README.md`, the
   service contract and the test customers. Do not edit anything in the folder. Nothing from it goes into code, prompts,
   tests or memory.
2. Reshape the mock from the contract with the checklist in `mock/README.md`: `customers.json` from the test customers,
   paths, request field names, response shapes, the ledger route, `openapi.json` replaced by the contract's. Keep the seven
   role names as the path segments (the renderer finds tools by them). `npx wrangler deploy`, then
   `python3 mock/check.py <mock url> <a test customer id>`: every tool must answer as the contract says and the ledger must
   hold what was sent. Fix and redeploy until it does.
3. Build with the helper: `python3 tools/hidden.py briefs/final/ <mock url> --team <name> --member "<name> <email>"`.
   It checks the mock serves `/openapi.json`, waits for the platform, runs the literal command
   `python3 builder/build.py briefs/final/ <mock url>` (2 to 3 minutes), keeps everything it prints in
   `traces/final.log`, checks the run and prints `submission.json` (also `work/submission.json`).
4. Read the trace while it runs: `documents:` (every file read, any NOT readable), `tool api:` (must say the mock's
   `/openapi.json`), the `policy:` lines (identity questions in order, calendar, bands, outcomes, transfers), every
   `ambiguity:` line, `fields:`, `dry run:`, and `self-test: chat probe` (a Turkish opening that names the customer). A
   reading you disagree with is noted for the write-up, never edited.
5. The helper's `check:` lines. `clean` means every required trace line is present, the export was read back from the
   platform with the trace's workflow id and counts, no fallback, no key. `trace (kept): ...` is informational.
6. Probe one test customer in Turkish: `FREYA_BANK_HOST=<mock url> python3 tools/probe.py final <customer id> "Evet, benim." ...`
   prints the agent's lines, the tool calls and the mock's ledger. Images in the zip are listed in the trace but not read:
   open them yourself and compare with the `policy:` lines.

## When a build must be repeated
- The helper builds once more by itself after a crash (no result line) or a fallback (`FAILED`, `bare template`,
  `rejected`, `out of time`) and prints the cause first. The slot is updated in place: the last run is the submission.
- A second failure the same way: `work/final/policy.json` is what the renderer got; the trace's last lines name the stage.
  The one allowed change is a crash fix that generalizes (a file type, a table shape, a field type the code did not expect),
  never a value, a name, a date or a reading from the case. Add a unit test for the shape, commit, run the helper again.
  If it cannot be fixed in 20 minutes, submit the bare-template agent of the last run with its trace.
- Never rerun to pick the nicer of two readings. Platform away: the helper waits up to 20 minutes before a build; inside a
  build the save retries until ten minutes before the cap. `export: written from the saved workflow` is noted, not rerun.

## 21:00 to 22:30: commit, submit, leave it alone
1. `python3 tools/hidden.py briefs/final/ <mock url> --team ... --commit` is a rebuild; to commit the existing run by hand:
   `git add briefs/final traces/final.log traces/final-*.log traces/final-*.policy.json final.workflow.json mock/customers.json mock/openapi.json mock/src mock/wrangler.toml`
   then commit and `git push`. The hash in the form is this commit; the trace's `builder:` line must say the tree was clean.
2. Make the repository public. Fill team and members in `work/submission.json` if the helper did not get them, and email it.
3. After sending, touch nothing: no edit to an export, no rebuild into the slot, no redeploy of the mock with other customers.

## Do not
- Do not change builder code, templates or prompts after 20:00 except a generalizing crash fix as above.
- Do not run a simulation of the final agent and do not write test customers from the case into the kit's test set.
- Never pipe a run through `head`; never start a simulation while one runs; one build at a time.
