# Submission form text (fill the two hashes and the hidden-brief ids at 20:00)

- Team: as registered.
- Repository: https://github.com/zkorkusuz/build-the-builder (private until submission; made public right before the form is sent).
- Commit: the hash printed by `git log --oneline -1` after the hidden builds are committed.
- Run command (from the repository root, after `source env` and the setup in the README):

```
.venv/bin/python builder/build.py briefs/<brief>.md [more brief files] briefs/<brief>.openapi.json
```

  Several brief files are listed before the API file. The slot name is the brief file names joined with `_`.
- Setup: `cp env.example env.sh`, fill the keys, `source env.sh`; `/opt/homebrew/bin/python3 -m venv .venv && .venv/bin/pip install claude-agent-sdk==0.2.165` (Python 3.10 or newer). A build takes about 2 minutes and about $0.60 of Claude credits; it never runs a simulation unless `--selftest` is given.
- Workflows: for each hidden brief, the `workflow_id` and `agent_id` from the build's last JSON line; the export file `<slot>.workflow.json` at the repository root.
- Traces: `traces/<slot>-<start>.log` (start and end, every model call with its purpose and cost, workflow and agent ids, step and tool counts, lint and dry-run results, the resolved tool field names, every ambiguity the normalize stage resolved) and `traces/<slot>-<start>.policy.json` (the policy that produced the agent).
- Practice evidence, if asked: `results/` is not committed; the tracker's run log and `docs/methodology.md` summarise it; `docs/figures/` holds the charts.
