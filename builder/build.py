"""Build a Freya phone agent from a bank's brief and its tool API file, with no manual step.

    python3 builder/build.py <brief.md> [more brief files] <openapi.json> [--no-adapt] [--selftest <cases.json> --brief-id A]

Stages: normalize (Claude) -> render (code) -> adapt (Claude) -> lint and dry run -> save and publish -> export -> optional self-test.
Writes a plain-text trace to traces/<slot>-<start>.log. Stops itself well inside 30 minutes and always leaves a saved workflow.
"""
import json, pathlib, shutil, subprocess, sys, time
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import freya
from builder import adapt, lint, llm, normalize, render

BUDGET_S = 27 * 60          # the rule is 30 minutes; keep a margin for the export and the trace


def main(argv):
    opts, files = parse(argv)
    briefs, spec_path = files[:-1], files[-1]
    slot = pathlib.Path(briefs[0]).stem
    start = time.time()
    ROOT.joinpath("traces").mkdir(exist_ok=True)
    log_path = ROOT / "traces" / (slot + "-" + time.strftime("%Y%m%d-%H%M%S") + ".log")
    trace = logger(log_path)
    trace("start " + time.strftime("%Y-%m-%dT%H:%M:%S%z") + " | briefs " + " ".join(briefs) + " | tool api " + spec_path + " | slot " + slot)
    left = lambda: BUDGET_S - (time.time() - start)
    workdir = isolate(slot, briefs, spec_path)
    spec = json.loads(pathlib.Path(spec_path).read_text())
    texts = [(pathlib.Path(b).name, pathlib.Path(b).read_text()) for b in briefs]

    policy = normalize.normalize(texts, pathlib.Path(spec_path).read_text(), workdir, trace, llm.ask, llm.parse_json)
    (workdir / "policy.json").write_text(json.dumps(policy, indent=1))
    trace("normalize: policy with " + str(len(policy.get("rules", []))) + " rules, " + str(len(policy.get("bands", []))) + " bands, " + str(len(policy.get("identity", {}).get("questions", []))) + " identity questions")

    workflow = render.render(policy, spec)
    trace("render: " + str(len(workflow["nodes"])) + " steps, " + str(count_tools(workflow)) + " tools, lint " + (" | ".join(lint.check(workflow)) or "clean"))
    saved = save(slot, workflow, trace)           # a valid agent exists from here on

    if not opts["no_adapt"] and left() > 6 * 60:
        try:
            adapted = adapt.adapt(json.loads(json.dumps(workflow)), policy, workdir, trace, llm.ask, llm.parse_json)
            if not lint.check(adapted):
                workflow, saved = adapted, save(slot, adapted, trace)
            else:
                trace("adapt: result failed lint, kept the rendered version")
        except Exception as e:
            trace("adapt: skipped after error " + str(e)[:200])
    export_path = ROOT / (slot + ".workflow.json")
    freya.export_workflow(saved["workflow_id"], str(export_path))
    trace("export: " + str(export_path))

    if opts["selftest"] and left() > 13 * 60:
        selftest(saved["agent_id"], opts, trace)
    elif opts["selftest"]:
        trace("self-test skipped: " + str(round(left() / 60)) + " minutes left")
    trace("end " + time.strftime("%Y-%m-%dT%H:%M:%S%z") + " | " + str(round(time.time() - start)) + " s | workflow " + saved["workflow_id"] + " | agent " + saved["agent_id"])
    print(json.dumps({"slot": slot, "workflow_id": saved["workflow_id"], "agent_id": saved["agent_id"], "export": str(export_path), "trace": str(log_path)}))


def parse(argv):
    opts, files, i = {"no_adapt": False, "selftest": None, "brief_id": None}, [], 0
    while i < len(argv):
        a = argv[i]
        if a == "--no-adapt": opts["no_adapt"] = True
        elif a == "--selftest": opts["selftest"] = argv[i + 1]; i += 1
        elif a == "--brief-id": opts["brief_id"] = argv[i + 1]; i += 1
        else: files.append(a)
        i += 1
    if len(files) < 2:
        sys.exit(__doc__)
    return opts, files


def logger(path):
    def trace(line):
        stamp = time.strftime("%H:%M:%S") + " " + line
        print(stamp, flush=True)
        with path.open("a") as f:
            f.write(stamp + "\n")
    return trace


def isolate(slot, briefs, spec_path):
    """A working folder for the model that holds only the briefs and the tool API file."""
    workdir = ROOT / "work" / slot
    shutil.rmtree(workdir, ignore_errors=True)
    workdir.mkdir(parents=True)
    for f in briefs + [spec_path]:
        shutil.copy(f, workdir / pathlib.Path(f).name)
    return workdir


def count_tools(workflow):
    return sum(len(n.get("tools", [])) + len(n.get("pre_actions", [])) for n in workflow["nodes"].values()) + len(workflow.get("tools", []))


def save(slot, workflow, trace):
    freya.validate_workflow(slot, workflow)
    saved = freya.save_workflow(slot, workflow, state_file=str(ROOT / ".freya-agents.json"))
    if "version" not in saved:                      # the first save only creates; the second sets the model and publishes
        saved = freya.save_workflow(slot, workflow, state_file=str(ROOT / ".freya-agents.json"))
    trace("freya: workflow " + saved["workflow_id"] + " agent " + saved["agent_id"] + " version " + str(saved.get("version")))
    return saved


def selftest(agent_id, opts, trace):
    cmd = [sys.executable, str(ROOT / "tools" / "run_cases.py"), agent_id, "--cases", opts["selftest"], "--out", str(ROOT / "results" / "selftest.json")]
    if opts["brief_id"]:
        cmd += ["--brief", opts["brief_id"]]
    trace("self-test: " + " ".join(cmd[1:]))
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=14 * 60).stdout
    for line in out.splitlines():
        if line.startswith(("PASS", "FAIL")) or "passed" in line:
            trace("self-test: " + line.strip()[:200])


if __name__ == "__main__":
    main(sys.argv[1:])
