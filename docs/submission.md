# Submission (send `submission.json` before 20:00 UTC = 23:00 Istanbul to the address in the kit email)

```json
{
  "team": "<as registered>",
  "members": [{"name": "<name>", "email": "<login email>"}],
  "repo": "https://github.com/zkorkusuz/build-the-builder",
  "commit": "<hash of the commit that holds the final folder, the trace, the export and mock/>",
  "run_command": "python3 builder/build.py {case_folder} {mock_url}",
  "workflow": "<slot>.workflow.json",
  "trace": "traces/final.log",
  "mock_url": "https://<worker>.<subdomain>.workers.dev"
}
```

- `python3` is the venv's interpreter after `source .venv/bin/activate` (Python 3.10 or newer, `claude-agent-sdk==0.2.165`)
  and `source env`; the README has the setup lines. `{case_folder}` is the unzipped folder; `{mock_url}` the deployed Worker.
- `traces/final.log` is everything the build printed (the `tee` file); the builder's own copy `traces/<slot>-<start>.log`
  and the policy it rendered `traces/<slot>-<start>.policy.json` are committed next to it.
- The export `<slot>.workflow.json` is written by `freya.export_workflow` right after the save; its workflow id and step
  and tool counts match the trace's `end` line.
- The repository is private until the files are committed and pushed; make it public right before sending.
