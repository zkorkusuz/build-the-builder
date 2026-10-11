"""Play a customer line by line against a slot's agent, with the bank at FREYA_BANK_HOST (our mock; the case id is one of its customers).

    FREYA_BANK_HOST=https://<mock> .venv/bin/python tools/probe.py <slot> <case id> "first line" "second line" ...

Unlike tools/chat.py it needs no entry in public-test-set.json, so it works for the final's test customers. Needs `source env`.
"""
import json, pathlib, sys, time
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
import chat, freya
slot, case_id, lines = sys.argv[1], sys.argv[2], sys.argv[3:]
workflow_id = json.loads((ROOT / ".freya-agents.json").read_text())[slot]["workflow_id"]
variables = chat.http("/v1/practice/sessions", {"case": case_id})["variables"]
print("variables:", variables)
start = {"workflowId": workflow_id, "customerVariables": variables}
call_id = chat.say(None, "Alo?", start)
for text in lines:
    print("YOU:", text)
    call_id = chat.say(call_id, text, start)
try:
    freya.api("POST", "/api/v2/chat/end", {"callId": call_id})
except Exception as e:
    print("(end:", str(e)[:120], ")")
print("\nTool calls:"); chat.print_tool_calls(call_id)
time.sleep(5)
print("\nLedger:", json.dumps(chat.http("/v1/practice/ledger/" + variables["customer_id"]), ensure_ascii=False)[:900])
