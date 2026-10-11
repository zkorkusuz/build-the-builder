# Build the Builder (Freya hackathon)

A builder: brief file(s) + tool API file in, a Freya phone agent (workflow) out, with no manual step.
Command: `python3 builder/build.py <brief.md> [more brief files] <openapi.json>`
The phone agent is scored on hidden customers: the bank's ledger must be exactly right and a judge model must find
no policy or honesty problem, in all 3 runs. Full plan and platform notes: `PLAYBOOK.md`.

This file is for the developer's Claude Code session. The builder must not read it: give the builder its own
working folder with only its skill, the brief(s) and the tool API file. `examples/agent_builder.py` runs Claude in
this folder with project settings, so on a hidden brief it could pick up Brief A values from here, PLAYBOOK.md,
the briefs or the public test set.

## Read first
- `PLAYBOOK.md`: the plan, scoring, platform gotchas
- `docs/sources.md`: the hackathon page and the τ^τ-bench paper, extracted with numbers and section references
- `docs/workflow-format.md`, `docs/tools-and-code.md`, `docs/api.md`: the only reliable source for the workflow JSON
- `briefs/brief-a.md`, `briefs/brief-b.md`, `tools/openapi.json`, `public-test-set.json`

## Hard rules
- Never hard-code anything from a brief (values, dates, names, outcomes, sentences) into builder code, templates or
  skills. Everything the agent needs comes from the brief at build time.
- The phone agent model is `AGENT_LLM` in `freya.py`. Never change it.
- The phone agent may call only the bank's tool API. Code steps and hooks inside the workflow are fine.
- Save workflows only with `freya.save_workflow(slot, workflow)`: one slot per brief (its file name), a separate slot
  for a second run. Export right after each run to a file named for that run. A workspace holds 200 workflows
  (hackathon page and README): still update one slot in place. `save_workflow` keeps its slot table in `.freya-agents.json`
  in the current folder, so a builder that runs in its own working folder passes `state_file` pointing at the kit
  root, which `tools/chat.py` reads.
- The builder runs in its own working folder and never reads `CLAUDE.md`, `PLAYBOOK.md`, the practice briefs or
  `public-test-set.json` during a build.
- A builder run takes at most 30 minutes, self-tests included, and always ends with a valid saved workflow.
- Every builder run writes a trace: start and end time; each model call (model, one-line purpose); workflow id,
  agent id, step and tool counts; each self-test and its result. Never write API keys into it.
- Never change a test's expected outcome to make the agent pass. Expectations come from the brief.
- One simulation runs at a time per workspace. Do not start a run while another is running.
- Do not probe or load-test the platform.

## Workflow JSON essentials (details in PLAYBOOK.md section 4.4)
- No `null`. Leave `agent_config` out. `save_workflow` publishes; a plain PUT does not.
- `tools` only on conversation steps; `pre_actions` only on api_request and code steps.
- `response_mapping` on the tool for `tools`, on the step for `pre_actions`; paths start with `data.`.
- Booleans arrive as strings: test `"true"` and `"True"`. Every passthrough step ends with an `always` transition.
- Code: use `vars`, never raise, no `{{` or `}}` in code. Fixed values use `default`, never `const`.
- Tool descriptions say when to call the tool. Post-hooks add `what_to_do_next` so the agent never goes silent.

## Commands
- `source env` (once per terminal; the file is `env`, not `env.sh`)
- `python3 tools/run_cases.py <agent_id> --brief A [--reps 3] [--style in_words] [--only PUB-01] [--out results/x.json]`
- `python3 tools/chat.py <slot> <case_id>`: play a practice customer turn by turn
- `.venv/bin/python tools/review_run.py results/<run>.json`: the review loop. For every failed call it prints the decision trail with its maker (code, hook, route, extraction, model) and the judge's reason. For each failure ask: which decision did the model make that code, a hook or a route could have made instead? Move it, rerun the failed cases with `--only`, then `--reps 3`.
- `python3 -c "import freya; print(freya.get_call('<call_id>')['messages'])"`: transcript with tool calls and events

## Code style
- Prefer the simplest code that works. No classes, frameworks or abstractions unless asked.
- Functions under ~30 lines with one job. Files under ~200 lines.
- Names say what things are. Comments explain why in one plain sentence, never what.
- Retries, timeouts and error handling live in one place (the Freya and LLM wrappers and the pipeline), not in every function.
- Standard library first. Ask before adding a dependency.
- Do not reformat the kit's own files (`freya.py`, `tools/`, `examples/`); change only what is needed.

## How to work with me
- Before coding: the plan in 3 to 5 plain bullets.
- After coding: what changed and why in 2 to 3 sentences.
- If a best practice would add a lot of code, say so and offer the simple version first.
