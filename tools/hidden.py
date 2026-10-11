"""Build the hidden briefs for submission, one after the other, and check each build before the next.

    python3 tools/hidden.py briefs/final/ https://<worker>.<subdomain>.workers.dev [--team NAME] [--member "Name <email>"] [--commit]
    python3 tools/hidden.py briefs/hidden-1.md briefs/hidden-1.openapi.json [briefs/hidden-2.md briefs/hidden-2.openapi.json] [--team NAME] [--commit]

A pair is a folder of documents and the address of our bank mock (the final's form; the mock must serve /openapi.json before
the build starts) or a brief file and its tool API file. For each pair it runs the one build command and keeps everything the build prints in traces/<brief>.log. Then it checks
the run: the trace has every line the organizers ask for, the export matches the trace, nothing fell back to the bare
template, no key leaked. A build that crashed or fell back is run once more, after its cause is printed; any other result
is kept as it is, so no run is ever chosen over another. At the end it prints the submission form. --commit commits the
briefs, the traces, the exports and, for the final's form, the mock, nothing else. Needs the venv active (python 3.10+) and `source env`.
"""
import json, os, pathlib, re, subprocess, sys, time, urllib.request
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import freya

# Markers are matched at the start of a trace line (after its time stamp), never inside it: the policy lines echo the brief's own words.
RERUN = ("render: FAILED", "normalize: FAILED", "design: FAILED", "save: the platform rejected", "save: failed, ", "tool api: FAILED")      # a crash or a fallback: build again
WARN = ("normalize: repairing", "normalize: still incomplete", "documents: NOT readable", "tool api: written by the model",
        "export: written from the saved workflow", "self-test: chat probe: no answer",
        "self-test: chat probe skipped", "self-test skipped", "adapt: skipped", "adapt: result failed lint", "dry run: skipped")
REQUIRED = ("start ", "builder: commit", "model call:", "dry run:", "freya: workflow", "export:", "self-test:", "end ")


def main(argv):
    opts = {"team": "<team>", "members": [], "commit": False}
    pairs = parse(argv, opts)
    preflight(pairs)
    results = {slot_of(brief): build_checked(brief, spec) for brief, spec in pairs}
    report(results, opts)


def parse(argv, opts):
    files, i = [], 0
    while i < len(argv):
        if argv[i] == "--team":
            opts["team"] = argv[i + 1]; i += 2
        elif argv[i] == "--member":                                      # "Name <email>"
            m = re.match(r"\s*(.*?)\s*<([^>]+)>\s*$", argv[i + 1])
            opts["members"].append({"name": m.group(1), "email": m.group(2)} if m else {"name": argv[i + 1], "email": ""}); i += 2
        elif argv[i] == "--commit":
            opts["commit"] = True; i += 1
        else:
            files.append(argv[i]); i += 1
    if len(files) < 2 or len(files) % 2:
        sys.exit(__doc__)
    pairs = [(b, mock_url_of(b, s)) for b, s in zip(files[::2], files[1::2])]
    bad = [b + " " + s for b, s in pairs if not (pathlib.Path(b).is_file() and pathlib.Path(s).is_file() or pathlib.Path(b).is_dir() and s.startswith("http"))]
    if bad:
        sys.exit("each pair is a brief file and its tool API file, or a folder of documents and the mock's address: " + "; ".join(bad))
    if len({slot_of(b) for b, _ in pairs}) < len(pairs):      # the name is the slot: equal names would overwrite one agent with the other
        sys.exit("brief files or folders need distinct names")
    return pairs


def mock_url_of(brief, spec):
    """The second item of a folder pair as a URL: a bare host gets its scheme; a file path or a brief file's API file stays as given."""
    if pathlib.Path(brief).is_dir() and "://" not in spec and not pathlib.Path(spec).exists():
        return "https://" + spec
    return spec


def slot_of(brief):
    """The slot the builder uses: the folder's name, or the brief file's name without its suffix."""
    return pathlib.Path(brief.rstrip("/")).name if pathlib.Path(brief).is_dir() else pathlib.Path(brief).stem


def preflight(pairs):
    """Stop before the first build when something is missing: a key, the interpreter, the SDK, the mock; warn about a dirty tree."""
    problems = []
    if not os.environ.get("FREYA_API_KEY"):
        problems.append("FREYA_API_KEY is not set: source env")
    if sys.version_info < (3, 10):
        problems.append("python " + sys.version.split()[0] + " is too old: source .venv/bin/activate")
    try:
        import claude_agent_sdk  # noqa: F401
    except ImportError:
        problems.append("claude_agent_sdk is not installed in this interpreter")
    for brief, url in pairs:
        if pathlib.Path(brief).is_dir() and not mock_answers(url):     # without it the build would fall back to model-written tool shapes that may not match the mock
            problems.append("the mock at " + url + " does not serve /openapi.json with paths; deploy it first (mock/README.md)")
    if problems:
        sys.exit("\n".join(problems))
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if dirty:
        print("note: " + str(len(dirty.splitlines())) + " tracked file(s) modified; commit them first so the trace names the commit that ran", flush=True)
    wait_for_platform()
    running = simulations_running()
    if running:
        print("note: a simulation is running (" + ", ".join(running) + "); a build starts none, so this only matters for a self-test", flush=True)


def mock_answers(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url.rstrip("/") + "/openapi.json", headers={"User-Agent": "Mozilla/5.0 build-the-builder"}), timeout=20) as r:
            return bool(json.loads(r.read().decode("utf-8")).get("paths"))
    except Exception:
        return False


def wait_for_platform(max_wait=20 * 60):
    """A build would spend its own budget waiting on the save when the platform is away; wait here instead."""
    t0 = time.time()
    while True:
        try:
            freya.api("GET", "/api/v2/workspaces"); return
        except Exception as e:
            if time.time() - t0 > max_wait: sys.exit("the platform has not answered for 20 minutes: " + str(e)[:120])
            print(time.strftime("%H:%M:%S") + " platform not answering (" + str(e)[:80] + "), again in 30 s", flush=True); time.sleep(30)


def simulations_running():
    try:
        r = freya.api("GET", "/api/v2/simulations")
        sims = (r.get("simulations") if isinstance(r, dict) else r) or []
        return [str(s.get("name") or s.get("id")) for s in sims if str(s.get("status")).lower() in ("running", "pending", "queued")]
    except Exception:
        return []


def build_checked(brief, spec):
    """Build and check; build once more only after a crash or a fallback. Returns the kept run."""
    for attempt in (1, 2):
        run = build(brief, spec)
        run["problems"], rerun = check(run["lines"], run["result"], read_export(run["result"]), secrets())
        for p in run["problems"]: print("  check: " + p, flush=True)
        print("  check: " + ("clean" if not run["problems"] else "done") + ", " + ("building once more" if rerun and attempt == 1 else "kept"), flush=True)
        if not rerun or attempt == 2:
            return run
        print("  cause: the lines above; the policy the renderer got is work/" + run["slot"] + "/policy.json. Fix only a crash, never a reading.", flush=True)


def build(brief, spec):
    """Run the one command and keep everything it prints in traces/<brief>.log."""
    stem = slot_of(brief)
    log = ROOT / "traces" / (stem + ".log")
    cmd = [sys.executable, "builder/build.py", brief, spec]
    print(time.strftime("%H:%M:%S") + " build " + stem + ": " + " ".join(cmd[1:]) + " -> traces/" + log.name, flush=True)
    lines = []
    with log.open("w") as f, subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env={**os.environ, "PYTHONUNBUFFERED": "1"}) as p:
        for line in p.stdout:
            print("  " + line, end="", flush=True); f.write(line); lines.append(line.rstrip("\n"))
    result = None
    for line in reversed(lines):                 # the build's last line is its result; a dict printed by a traceback is not
        if line.startswith('{"slot"'):
            try:
                result = json.loads(line)
            except ValueError:
                pass
            break
    return {"slot": stem, "brief": brief, "spec": spec, "log": "traces/" + log.name, "lines": lines, "result": result, "exit": p.returncode}


def read_export(result):
    try:
        return json.loads(pathlib.Path(result["export"]).read_text())
    except Exception:
        return None


def secrets():
    """Every secret in the environment, to be sure none of them is in what we commit."""
    return {k: v for k, v in os.environ.items() if any(w in k for w in ("KEY", "TOKEN", "SECRET")) and len(v) >= 8 and not v.startswith("http")}


def check(lines, result, export, secret_values):
    """Problems with one build and whether it must be built again: no result, a fallback, an export unlike the trace, a leaked key."""
    if result is None:
        return ["the build printed no result line: it crashed or was cut off"], True
    problems, rerun = [], False
    bodies = [body(line) for line in lines]
    for text in bodies:
        if text.startswith(RERUN):
            problems.append("trace: " + text[:160]); rerun = True
        elif text.startswith(WARN) or (text.startswith("self-test: chat probe:") and "names the customer: no" in text):
            problems.append("trace (kept): " + text[:160])
    problems += ["trace: no '" + name.strip() + "' line" for name in REQUIRED if not any(text.startswith(name) for text in bodies)]
    problems += check_export(result, export)
    text = "\n".join(lines) + json.dumps(export or {})
    problems += ["secret " + name + " appears in the trace or the export" for name, value in secret_values.items() if value in text]
    return problems, rerun


def body(line):
    """A trace line without its time stamp; any other printed line as it is."""
    return line[9:] if re.match(r"\d\d:\d\d:\d\d ", line) else line


def check_export(result, export):
    """The export is what the organizers score: it must be the platform's copy of the workflow the trace describes."""
    if export is None:
        return ["export: file missing or not JSON"]
    w = export.get("workflow") or {}
    nodes = w.get("nodes") or {}
    tools = sum(len(n.get("tools", [])) + len(n.get("pre_actions", [])) for n in nodes.values()) + len(w.get("tools", []))
    problems = []
    if export.get("workflow_id") != result.get("workflow_id"): problems.append("export: workflow id differs from the trace")
    if (len(nodes), tools) != (result.get("steps"), result.get("tools")):
        problems.append("export: " + str(len(nodes)) + " steps and " + str(tools) + " tools, the trace says " + str(result.get("steps")) + " and " + str(result.get("tools")))
    if "exported_from" in export: problems.append("export: written from the saved workflow, not read back from the platform")
    return problems


def report(results, opts):
    """The summary and the submission form, with the commit hash when --commit made the commit."""
    print("\nbuilds:")
    for name, r in results.items():
        res = r["result"] or {}
        print("  " + name + ": workflow " + str(res.get("workflow_id")) + " agent " + str(res.get("agent_id")) + " version " + str(res.get("version"))
              + ", " + str(res.get("steps")) + " steps, " + str(res.get("tools")) + " tools, " + str(len(r["problems"])) + " check note(s)")
    commit = do_commit(results) if opts["commit"] else "<hash of the commit that holds the files below>"
    form = submission(results, opts, commit)
    (ROOT / "work").mkdir(exist_ok=True); (ROOT / "work" / "submission.json").write_text(json.dumps(form, indent=2))
    print("\nsubmission.json (also in work/submission.json):\n" + json.dumps(form, indent=2))


def submission(results, opts, commit):
    """The form the page asks for: one case with its mock (the final's form), or one workflow and trace per brief file."""
    head = {"team": opts["team"], "members": opts["members"] or [{"name": "<name>", "email": "<login email>"}], "repo": repo_url(), "commit": commit}
    exports = {n: relative((r["result"] or {}).get("export")) or "<no export>" for n, r in results.items()}
    run = next(iter(results.values()))
    if len(results) == 1 and pathlib.Path(run["brief"]).is_dir():
        return {**head, "run_command": "python3 builder/build.py {case_folder} {mock_url}", "workflow": exports[run["slot"]], "trace": run["log"], "mock_url": run["spec"]}
    return {**head, "run_command": "python3 builder/build.py {brief_path} {tool_api_path}", "workflows": exports, "traces": {n: r["log"] for n, r in results.items()}}


def relative(path):
    """The path inside the repository, or None when the file is outside it (then it cannot be committed)."""
    try:
        return str(pathlib.Path(path).resolve().relative_to(ROOT))
    except (ValueError, TypeError):
        return None


def do_commit(results):
    """Commit each brief (or document folder), its API file (or the mock), the console log, the builder's own trace and policy, and the export. Nothing else."""
    wanted = []
    for r in results.values():
        res = r["result"] or {}
        wanted += [r["brief"], r["spec"], r["log"], res.get("trace"), res.get("export")]
        if pathlib.Path(r["brief"]).is_dir():                     # the agent was built against this mock, so the scored run needs it as it was
            wanted += [str(ROOT / "mock" / x) for x in ("customers.json", "openapi.json", "wrangler.toml", "src")]
        if res.get("trace"):
            wanted.append(pathlib.Path(res["trace"]).with_suffix(".policy.json"))
    files = [relative(p) for p in wanted if p and pathlib.Path(p).exists()]
    for p, f in zip([p for p in wanted if p and pathlib.Path(p).exists()], files):
        if f is None:
            print("  not committed, outside the repository: " + str(p), flush=True)
    subprocess.run(["git", "add", "--"] + [f for f in files if f], cwd=ROOT, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "Built for submission: " + ", ".join(results)], cwd=ROOT, check=True)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def repo_url():
    url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return url.replace("git@github.com:", "https://github.com/").removesuffix(".git") or "<repository url>"


if __name__ == "__main__":
    main(sys.argv[1:])
