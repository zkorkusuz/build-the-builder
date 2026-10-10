"""Talk to one of your workflows turn by turn, as a practice customer.

    python3 tools/chat.py <slot> <case_id>        for example: python3 tools/chat.py base PUB-01

<slot> is the name you gave freya.save_workflow. The slots are stored in .freya-agents.json in the folder where
save_workflow ran, so run save_workflow and this script from the kit folder. Save a new workflow twice before
chatting: the second save sets the event model, which a chat turn needs.

You type what the customer says. Type /end to hang up. Afterwards it prints the tool calls of the call
and the bank's ledger for this practice customer.

Not tested against the platform yet: if a field name differs, check docs/api.md ("Talk to your workflow turn by turn").
Needs FREYA_API_KEY and FREYA_BANK_TEAM_KEY (source env.sh).
"""
import json, pathlib, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
import freya
from score import http


def say(call_id, text, start):
    """Send one customer turn. The first turn starts the call with the workflow and the customer's variables."""
    body = dict(start, message=text) if call_id is None else {"callId": call_id, "message": text}
    try:
        r = freya.api("POST", "/api/v2/chat/message", body)
    except Exception as e:             # a long turn can return 504 or time out; type the same line again
        print("  (error:", str(e)[:300], ")")
        return call_id
    print("AGENT:", r.get("response"))
    return r.get("callId", call_id)


def print_tool_calls(call_id):
    """Tool calls and their results, read from the call's system events."""
    for m in freya.get_call(call_id).get("messages", []):
        if m.get("role") != "system":
            continue
        try:
            e = json.loads(m.get("message") or "{}")
        except ValueError:
            continue
        if e.get("event") == "function_call_start":
            args = e.get("args") or {}
            print(f"  call    {e.get('function', '')}  {json.dumps(args.get('body', args))[:300]}")
        elif e.get("event") == "function_call_complete":
            print(f"  result  {e.get('function', '')}  {json.dumps(e.get('result'))[:300]}")
        elif e.get("event") == "error":
            print(f"  error   {json.dumps(e.get('message'))[:300]}")


def main(slot, case_id):
    workflow_id = json.loads((ROOT / ".freya-agents.json").read_text())[slot]["workflow_id"]
    case = next(c for c in json.load(open(ROOT / "public-test-set.json")) if c["id"] == case_id)
    variables = http("/v1/practice/sessions", {"case": case_id})["variables"]
    name = f"{variables.get('first_name', '')} {variables.get('last_name', '')}".strip()
    print(f"You play {name} ({case['title']}). Identity: {case['identity']}")
    print(f"Script: {case['script']}\nType /end to hang up.\n")

    start = {"workflowId": workflow_id, "customerVariables": variables}
    call_id = say(None, "Hello?", start)
    while True:
        text = input("YOU:   ").strip()
        if text == "/end":
            break
        call_id = say(call_id, text, start)

    if call_id:
        try:
            freya.api("POST", "/api/v2/chat/end", {"callId": call_id})
        except Exception as e:         # the agent may already have hung up
            print("  (end:", str(e)[:200], ")")
        print("\nTool calls:")
        print_tool_calls(call_id)
    time.sleep(5)                      # close_call runs after the call ends, so the ledger can lag a little
    print("\nLedger:", json.dumps(http("/v1/practice/ledger/" + variables["customer_id"]), indent=1))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
