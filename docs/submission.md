# Submission form (send before 20:00 UTC = 23:00 Istanbul to the address in the kit email)

`tools/hidden.py` prints this form filled in (and writes it to `work/form.json`); with `--commit` it also makes the commit and fills the hash.

```json
{
  "team": "<as registered>",
  "repo": "https://github.com/zkorkusuz/build-the-builder",
  "commit": "<hash of the commit that holds the briefs, traces and exports>",
  "run_command": "python3 builder/build.py {brief_path} {tool_api_path}",
  "workflows": {
    "hidden-1": "hidden-1.workflow.json",
    "hidden-2": "hidden-2.workflow.json"
  },
  "traces": {
    "hidden-1": "traces/hidden-1.log",
    "hidden-2": "traces/hidden-2.log"
  }
}
```

- The run command is literal: `python3` is the venv's interpreter (`source .venv/bin/activate`, Python 3.10 or newer, `claude-agent-sdk==0.2.165`)
  after `source env.sh`; the README has the four setup lines. `{brief_path}` is the one Markdown file of a hidden brief, `{tool_api_path}` its API file.
- `traces/<brief>.log` is everything the build printed (the organizers' `tee` file). The builder's own copy, `traces/<brief>-<start>.log`, and the
  policy it rendered, `traces/<brief>-<start>.policy.json`, are committed next to it.
- The export `<brief>.workflow.json` at the repository root is written by `freya.export_workflow` right after the save. Its `workflow_id` and step
  and tool counts match the trace's `end` line; `tools/hidden.py` checks that.
- The repository is private until the files are committed and pushed; make it public right before sending the form.
- Optional: Claude Code session logs may be shared with the write-up (`docs/presentation.md`, `docs/methodology.md`).
