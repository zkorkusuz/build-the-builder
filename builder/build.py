"""Build a Freya phone agent from a bank's brief and its tool API file, or from a folder of the bank's documents and the address of its mock, with no manual step.

    python3 builder/build.py <brief.md> [more brief files] <openapi.json> [--no-adapt] [--policy <policy.json>] [--selftest <cases.json> --brief-id A]
    python3 builder/build.py <folder of documents> <mock url>

Stages: normalize (Claude) -> render (code) -> adapt (Claude) -> lint and dry run -> save and publish -> export -> optional self-test.
Writes a plain-text trace to traces/<slot>-<start>.log. Stops itself well inside 30 minutes and always leaves a saved workflow.
--policy skips the normalize stage and renders from a given policy file (for tests; never for a hidden brief).
"""
import json, pathlib, re, shutil, subprocess, sys, time, urllib.request
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import freya
from builder import adapt, documents, lint, llm, normalize, render, selfcheck

BUDGET_S = 27 * 60          # the rule is 30 minutes; keep a margin for the export and the trace


def main(argv):
    opts, files = parse(argv)
    folder, mock_url = source(files)
    briefs, spec_path = ([folder] if folder else files[:-1]), (None if folder else files[-1])
    slot = pathlib.Path(folder.rstrip("/")).name if folder else "_".join(pathlib.Path(b).stem for b in briefs)   # one slot per brief set; the same set updates the same workflow
    start = time.time()
    ROOT.joinpath("traces").mkdir(exist_ok=True)
    log_path = ROOT / "traces" / (slot + "-" + time.strftime("%Y%m%d-%H%M%S") + ".log")
    trace = logger(log_path)
    trace("start " + time.strftime("%Y-%m-%dT%H:%M:%S%z") + (" | documents " + folder + " | mock " + mock_url if folder else " | briefs " + " ".join(briefs) + " | tool api " + spec_path) + " | slot " + slot)
    trace(selfcheck.describe_run(sys.argv))
    left = lambda: BUDGET_S - (time.time() - start)
    given = json.loads(pathlib.Path(opts["policy"]).read_text()) if opts["policy"] else None   # read before the work folder is wiped
    workdir = isolate(slot, briefs, spec_path)
    ask = lambda prompt, wd, tr, purpose: llm.ask(prompt, wd, tr, purpose, timeout=min(600, left() - 120))
    texts = documents.folder_to_briefs(folder) if folder else [(pathlib.Path(b).name, pathlib.Path(b).read_text()) for b in briefs]
    if folder:
        unread = [n for n, t in texts if t.removeprefix("# Document: " + n).lstrip().startswith(("not readable", "pdf not readable", "skipped"))]
        trace("documents: " + str(len(texts)) + " read in this order: " + ", ".join(n for n, _ in texts))
        trace("documents: " + ("NOT readable: " + ", ".join(unread) if unread else "every document readable") + " | image files listed, not read: " + str(len(documents.image_paths(folder))))
    spec = tool_spec(spec_path, mock_url, texts, workdir, trace, ask)
    (workdir / "openapi.json").write_text(json.dumps(spec, indent=1))

    policy = given if given is not None else read_policy(opts, texts, json.dumps(spec, indent=1), workdir, trace, ask)
    if given is not None:
        trace("normalize: skipped, policy from " + opts["policy"])
    (workdir / "policy.json").write_text(json.dumps(policy, indent=1))
    try:
        workflow = render.render(policy, spec)
    except Exception as e:
        trace("render: FAILED on this policy, " + str(e)[:200] + "; rendering the bare template")
        workflow = render.render({}, spec)
    trace("render: " + str(len(workflow["nodes"])) + " steps, " + str(count_tools(workflow)) + " tools, lint " + (" | ".join(lint.check(workflow)) or "clean"))
    trace("render: steps " + ", ".join(workflow["nodes"]) + "; rule homes: dates, floors, offers and outcomes in code steps; tool results and guards in hooks; call flow in routes; the brief's sentences in fixed lines and prompts")
    try:
        trace("fields: " + json.dumps({t: {r: n for r, n in m.items() if n != r} for t, m in render.field_names(policy, spec).items() if any(n != r for r, n in m.items())} or "the role names, as in the practice file"))
    except Exception as e:                        # a malformed api_fields section must not stop the build before the save
        trace("fields: could not be listed (" + str(e)[:120] + ")")
    try:
        saved = save(slot, workflow, trace, left)     # a valid agent exists from here on
    except Rejected as e:
        trace("save: the platform rejected the workflow (" + str(e) + "); saving the bare template")
        workflow = render.render({}, spec)
        saved = save(slot, workflow, trace, left)

    if not opts["no_adapt"] and not opts["policy"] and left() > 6 * 60:
        try:
            adapted = adapt.adapt(json.loads(json.dumps(workflow)), policy, workdir, trace, ask, llm.parse_json)
            if not lint.check(adapted):
                workflow, saved = adapted, save(slot, adapted, trace, left)
            else:
                trace("adapt: result failed lint, kept the rendered version")
        except Exception as e:
            trace("adapt: skipped after error " + str(e)[:200])
    export_path = ROOT / (slot + ".workflow.json")
    try:
        freya.export_workflow(saved["workflow_id"], str(export_path))
    except Exception as e:                        # the platform read failed: the file still holds the workflow exactly as it was saved
        export_path.write_text(json.dumps({"workflow_id": saved["workflow_id"], "agent_id": saved["agent_id"], "exported_from": "the workflow as sent, the platform did not answer the read", "workflow": workflow}, indent=1))
        trace("export: written from the saved workflow after " + str(e)[:120])
    trace("export: " + str(export_path))
    (ROOT / "traces" / (log_path.stem + ".policy.json")).write_text(json.dumps(policy, indent=1))   # the policy that produced this agent, kept with its trace for audit

    selfcheck.probe(saved["workflow_id"], trace, left)
    if opts["selftest"] and left() > 13 * 60:
        selftest(saved["agent_id"], opts, trace)
    elif opts["selftest"]:
        trace("self-test skipped: " + str(round(left() / 60)) + " minutes left")
    steps, tools = len(workflow["nodes"]), count_tools(workflow)
    trace("end " + time.strftime("%Y-%m-%dT%H:%M:%S%z") + " | " + str(round(time.time() - start)) + " s | workflow " + saved["workflow_id"] + " | agent " + saved["agent_id"]
          + " | version " + str(saved.get("version")) + " | " + str(steps) + " steps | " + str(tools) + " tools")
    print(json.dumps({"slot": slot, "workflow_id": saved["workflow_id"], "agent_id": saved["agent_id"], "version": saved.get("version"), "steps": steps, "tools": tools,
                      "export": str(export_path), "trace": str(log_path)}))


def read_policy(opts, texts, spec_text, workdir, trace, ask):
    """The policy from --policy, or from the normalize stage. On a total failure, an empty policy still yields a saved agent."""
    try:
        policy = normalize.normalize(texts, spec_text, workdir, trace, ask, llm.parse_json)
    except Exception as e:
        trace("normalize: FAILED, " + str(e)[:300] + "; rendering from whatever came back")
        policy = {}
    trace("normalize: policy with " + str(len(policy.get("rules", []))) + " rules, " + str(len(policy.get("bands", []))) + " bands, "
          + str(len(policy.get("identity", {}).get("questions", []))) + " identity questions, " + str(len(policy.get("end_reasons", []))) + " end reasons")
    for line in summary(policy):
        trace("policy: " + line)
    return policy


def summary(p):
    """The policy's structured facts, one line each, so a reviewer can check the trace against the brief without the JSON."""
    g = lambda *ks: _dig(p, ks)
    lines = ["identity questions in order: " + ", ".join(str(q.get("field")) for q in g("identity", "questions") or []) + "; wrong answers that end the check: " + str(g("identity", "max_wrong_total")),
             "calendar: business weekdays " + str(g("calendar", "business_weekdays")) + ", holidays " + ", ".join(g("calendar", "holidays") or []),
             "callback window: " + str(g("callback", "days")) + " " + str(g("callback", "from")) + "-" + str(g("callback", "to")) + ", asks for another time: " + str(g("callback", "max_asks")),
             "confirmation asks allowed: " + str(g("confirmation", "max_asks")), "attempt-1 rule: " + str(g("attempt1_rule", "rule"))]
    for b in g("bands") or []:
        lines.append("band " + str(b.get("name")) + ": " + str(b.get("days_late_min")) + "-" + str(b.get("days_late_max")) + " days late, latest date the " + str(b.get("deadline_business_days")) + "th business day, " + str(b.get("attempts")) + " attempt(s)")
    lines.append("outcomes: " + "; ".join(k + " -> " + str(v.get("outcome")) + ("/" + str(v.get("reason")) if v.get("reason") else "") for k, v in (g("outcomes") or {}).items()))
    lines.append("end reasons: " + "; ".join(str(e.get("key")) + " -> " + str(e.get("outcome")) + ("/" + str(e.get("reason")) if e.get("reason") else "") + (" note " + str(e.get("note_reason")) if e.get("note_reason") else "") for e in g("end_reasons") or []))
    lines.append("transfers: " + "; ".join(str(t.get("queue")) + " -> " + str(t.get("outcome")) + ("/" + str(t.get("reason")) if t.get("reason") else "") for t in g("transfers") or []))
    lines.append("multi-product: " + str(g("multi_product", "enabled")) + "; floor fields: " + str(g("floor_field")) + "; no-reason outcomes: " + str(g("no_reason_outcomes")))
    for a in g("ambiguities") or []:
        lines.append("ambiguity: " + str(a))
    return lines


def _dig(d, keys):
    for k in keys:
        d = d.get(k) if isinstance(d, dict) else None
    return d


SPEC_PROMPT = """The documents below include a bank's service contract: the services a phone agent calls to check a customer's identity, read the late products, record a payment promise, add a note, book a callback, transfer the call and close it.
Write an OpenAPI 3.0 JSON for them: one POST path per service, named by its role from this list exactly: verify_identity, get_account, create_promise, add_note, schedule_callback, transfer_to_agent, close_call (leave out a role the contract has no service for; put the contract's own service name in the summary).
The application/json request body lists the property names, types, enums, descriptions and required fields exactly as the contract spells them, and the 200 response schema lists the response field names exactly as the contract gives them. Answer with the JSON only, in a ```json fence.

"""


def tool_spec(spec_path, mock_url, texts, workdir, trace, ask):
    """The tool API: the given file, else the mock's own /openapi.json, else one the model writes from the service contract."""
    if spec_path:
        return json.loads(pathlib.Path(spec_path).read_text())
    base = mock_url.rstrip("/")
    spec = fetch_json(base + "/openapi.json")
    if spec and spec.get("paths"):
        trace("tool api: " + base + "/openapi.json, " + str(len(spec["paths"])) + " paths")
    else:
        try:
            spec = llm.parse_json(ask(SPEC_PROMPT + normalize.documents_text(texts), workdir, trace, "tool api: OpenAPI from the service contract"))
            trace("tool api: written by the model from the documents, " + str(len(spec.get("paths") or {})) + " paths")
        except Exception as e:
            spec = json.loads((ROOT / "tools" / "openapi.json").read_text())       # the kit's shapes keep the build alive; the trace says so
            trace("tool api: FAILED to read or derive one (" + str(e)[:120] + "); using the kit's tool shapes")
    given = str((spec.get("servers") or [{}])[0].get("url") or "")
    if not given.startswith(base):                                  # the agent's tools call the mock, whatever the file says; a path prefix such as /v1 is kept
        spec["servers"] = [{"url": base + (re.sub(r"^https?://[^/]*", "", given).rstrip("/") if "://" in given else "")}]
    return spec


def fetch_json(url, tries=3):
    for _ in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 build-the-builder"}), timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            time.sleep(3)
    return None


def source(files):
    """The final's form (a folder of documents and the mock's address) or the practice form (brief files and an API file)."""
    folder = next((f for f in files if pathlib.Path(f).is_dir()), None)
    url = next((f for f in files if f.startswith(("http://", "https://"))), None)
    if folder and not url and len(files) == 2:                      # a bare host is the mock's address without its scheme
        url = "https://" + next(f for f in files if f != folder)
    if (folder is None) != (url is None):
        sys.exit("a folder of documents goes with the mock's address (python3 builder/build.py <folder> <mock url>)")
    return folder, url


def parse(argv):
    opts, files, i = {"no_adapt": False, "selftest": None, "brief_id": None, "policy": None}, [], 0
    while i < len(argv):
        a = argv[i]
        if a == "--no-adapt": opts["no_adapt"] = True
        elif a in ("--selftest", "--brief-id", "--policy"): opts[a[2:].replace("-", "_")] = argv[i + 1]; i += 1
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
    """A working folder for the model that holds only the briefs (or the document folder) and the tool API file."""
    workdir = ROOT / "work" / slot
    shutil.rmtree(workdir, ignore_errors=True)
    workdir.mkdir(parents=True)
    for f in briefs + ([spec_path] if spec_path else []):
        if pathlib.Path(f).is_dir():
            shutil.copytree(f, workdir / "documents")
        else:
            shutil.copy(f, workdir / pathlib.Path(f).name)
    return workdir


def count_tools(workflow):
    return sum(len(n.get("tools", [])) + len(n.get("pre_actions", [])) for n in workflow["nodes"].values()) + len(workflow.get("tools", []))


class Rejected(Exception):
    """The platform answered 4xx: the workflow itself is at fault, so retrying it is pointless."""


def save(slot, workflow, trace, left=lambda: 1800):
    """Validate, then save until it works: a platform hiccup must not end a build without a workflow.
    One attempt can take up to seven minutes inside the wrapper's own retries, so retrying stops ten minutes before the budget ends."""
    try:
        freya.validate_workflow(slot, workflow)
        trace("dry run: the platform accepted the workflow")
    except Exception as e:
        if "-> 4" in str(e):
            raise Rejected(str(e)[:160]) from None
        trace("dry run: skipped, " + str(e)[:160])
    while True:
        try:
            saved = freya.save_workflow(slot, workflow, state_file=str(ROOT / ".freya-agents.json"))
            if "version" not in saved:                      # the first save only creates; the second sets the model and publishes
                saved = freya.save_workflow(slot, workflow, state_file=str(ROOT / ".freya-agents.json"))
            break
        except Exception as e:
            if "-> 4" in str(e):
                raise Rejected(str(e)[:160]) from None
            trace("save: failed, " + str(e)[:160] + ("; trying again in 20 s" if left() > 600 else "; out of time"))
            if left() <= 600:
                raise
            time.sleep(20)
    trace("freya: workflow " + saved["workflow_id"] + " agent " + saved["agent_id"] + " version " + str(saved.get("version")))
    return saved


def selftest(agent_id, opts, trace):
    cmd = [sys.executable, str(ROOT / "tools" / "run_cases.py"), agent_id, "--cases", opts["selftest"], "--out", str(ROOT / "results" / "selftest.json")]
    if opts["brief_id"]:
        cmd += ["--brief", opts["brief_id"]]
    trace("self-test: " + " ".join(cmd[1:]))
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=14 * 60).stdout
    except subprocess.TimeoutExpired:
        trace("self-test: stopped after 14 minutes without a result")
        return
    for line in out.splitlines():
        if line.startswith(("PASS", "FAIL")) or "passed" in line:
            trace("self-test: " + line.strip()[:200])


if __name__ == "__main__":
    main(sys.argv[1:])
