# Runbook for the final (Sunday 20:00 to 22:30 Istanbul)

The page changed the final on Sunday: one case, Freya Bank's card statement-debt line, in Turkish; one zip of documents;
a bank mock we host on Cloudflare Workers; one `submission.json` with `mock_url`. This replaces `docs/runbook-2000.md`.

## Before 20:00
- `source env`; `.venv/bin/python -m unittest discover -s tests -q` passes; `git status` clean on the submission commit.
- Cloudflare: `cd mock && npx wrangler whoami` shows the account; the workers.dev subdomain is registered (dashboard,
  Workers, Subdomain) and `curl https://<worker>.<subdomain>.workers.dev/openapi.json` answers.
- The dashboard shows no running simulation.

## 20:00 to 21:00: the mock first, then one build
1. Unzip into `briefs/final/` (keep the folder name the zip gives; it becomes the slot). Read `BRIEF.md`, then `README.md`,
   then the service contract and the test customers. Do not edit anything in the folder.
2. Reshape the mock from the contract, following the checklist in `mock/README.md`: paths, request field names and enums,
   response shapes, the ledger route the organizers read, and `mock/customers.json` from the test customers. Keep the
   seven role names in `mock/openapi.json` paths (verify_identity, get_account, create_promise, add_note, schedule_callback,
   transfer_to_agent, close_call); the renderer finds tools by those names. `npx wrangler deploy`, then curl one tool call.
3. Build: `.venv/bin/python builder/build.py briefs/final/ https://<worker>.<subdomain>.workers.dev 2>&1 | tee traces/final.log`.
   Read the first lines: `documents:` lists every file read in order, `tool api:` says where the tool shapes came from,
   `policy:` lines show the identity questions, calendar, bands, outcomes; `ambiguity:` lines name what the model could
   not settle. `fields:` shows renamed request fields.
4. Probe in Turkish with one chat turn per step (`tools/chat.py` needs a practice case; use `POST /api/v2/chat/message`
   with the test customer's variables and `FREYA_BANK_HOST` pointing at the mock when scoring by hand).
5. A crash on a file type or shape: fix the crash only, rerun the build, keep the new trace. Never write a value, name
   or rule from the zip into `builder/` or `mock/src` beyond what the contract requires of the mock.

## 21:00 to 22:30: export, commit, submit
- The export is `<slot>.workflow.json` at the repository root, written right after the save; the trace is
  `traces/<slot>-<start>.log` plus the `tee` file. Commit the folder, the trace, the export and `mock/` together.
- Make the repository public, then email `submission.json` (text in `docs/submission.md`) before 23:00; aim for 22:30.
- Keep the mock deployed until results are out. Do not redeploy with other customers after submitting.
