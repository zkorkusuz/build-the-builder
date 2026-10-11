"""What a reviewer needs to tie a trace to the code and to the live agent: the run's description and one chat turn with the agent."""
import pathlib, platform, subprocess, sys, time
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import freya


def describe_run(argv):
    """One line: the commit the builder ran from (and whether the tree was clean), the interpreter and the exact command."""
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=10).stdout.strip() or "unknown"
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, capture_output=True, text=True, timeout=10).stdout.strip()
        commit += " with uncommitted changes to " + str(len(dirty.splitlines())) + " tracked file(s)" if dirty else " (clean tree)"
    except Exception:
        commit = "unknown (no git)"
    return "builder: commit " + commit + " | python " + platform.python_version() + " | " + pathlib.Path(sys.executable).name + " " + " ".join(argv)


def probe(workflow_id, trace, left, test_variables=None):
    """One chat turn with the published agent: proves the workflow can start a call and speaks its opening with the call's variables.
    The customer is made up (no practice case exists for a hidden brief); the chat is ended right after. Never fails the build."""
    if left() < 14 * 60:                     # two calls, each up to 6.5 minutes inside the wrapper's retries, must stay inside the cap
        trace("self-test: chat probe skipped, " + str(round(left() / 60)) + " minutes left")
        return
    variables = {"first_name": "Probe", "last_name": "Customer", "title": "Ms", "customer_id": "probe-0000", "now": time.strftime("%Y-%m-%dT%H:%M")}
    variables.update({k: str(v) for k, v in (test_variables or {}).items()})     # a designed workflow names its own call variables
    t0 = time.time()
    try:
        r = freya.api("POST", "/api/v2/chat/message", {"workflowId": workflow_id, "customerVariables": variables, "message": "Hello?"})
        reply = " ".join(str(r.get("response") or "").split())
        trace("self-test: chat probe: the agent answered 'Hello?' after " + str(round(time.time() - t0)) + " s, names the customer: "
              + ("yes" if "Customer" in reply else "no") + ", said: " + (reply[:220] or "(nothing)"))
        if r.get("callId"):
            freya.api("POST", "/api/v2/chat/end", {"callId": r["callId"]})
    except Exception as e:
        trace("self-test: chat probe: no answer after " + str(round(time.time() - t0)) + " s, " + str(e)[:160])
