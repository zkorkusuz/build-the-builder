"""Render a Freya workflow from a policy and the bank's tool API file. Pure: no network."""
import json, pathlib
from builder import dates, hooks, prompts

DATES_SRC = pathlib.Path(dates.__file__).read_text()
# Variables the workflow sets itself. A model-filled tool field must not share one of these names.
OWN_VARS = {"today", "now", "outcome", "reason", "products", "debt_summary", "product_count", "id_state", "transfer_state",
            "callback_state", "promise_state", "end_reason", "who", "identity_signal", "third_party_result", "conversation_done"}
HELPERS = """
def _load(name, default):
    try:
        v = vars.get(name)
        if isinstance(v, str) and v:
            return json.loads(v)
        if isinstance(v, (list, dict)):
            return v
    except Exception:
        pass
    return default
"""


def lit(value):
    return hooks.literal(value)


def always(target):
    return {"target_node": target, "description": "always", "condition": {"operator": "always"}}


def when(target, description, *pairs):
    """Transition that fires when any (variable, value) pair matches, both spellings for booleans."""
    conds = []
    for var, val in pairs:
        conds.append({"variable": var, "operator": "equals", "operand": str(val)})
        if str(val) in ("true", "True"):
            conds.append({"variable": var, "operator": "equals", "operand": "True" if str(val) == "true" else "true"})
    return {"target_node": target, "description": description, "condition": {"logic": "or", "conditions": conds}}


def code_node(name, code, target, before=()):
    assert "{{" not in code and "}}" not in code, name
    fn = {"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
          "parameters": {"type": "object", "properties": {"code": {"type": "string", "default": code}, "timeout_ms": {"type": "number", "default": 10000}}}}}
    return {"name": name, "node_type": "code", "passthrough": True, "passthrough_default_transition": target, "on_enter": {"type": "silent"},
            "disable_inactivity_monitor": True, "pre_actions": [fn], "transitions": list(before) + [always(target)]}


def end_node(name, spoken):
    params = {"message_mode": {"type": "string", "default": "custom" if spoken else "none"}}
    if spoken:
        params["spoken_message"] = {"type": "string", "default": spoken}
    return {"name": name, "node_type": "end_call", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "transitions": [],
            "terminal": {"type": "function", "function": {"name": name, "handler": "__function__:end_call", "parameters": {"type": "object", "properties": params}}}}


def extraction(name, values, description):
    return {"name": name, "type": "string", "enum_values": values, "description": description, "min_confidence": 0.6}


def tool(spec, name, hook_map, descriptions, mapping=None, retries=0, lifecycle=None):
    """An api_call tool for one path of the OpenAPI file. customer_id is baked; other fields are model-filled."""
    base = (spec.get("servers") or [{}])[0].get("url", "").rstrip("/")
    op = spec["paths"]["/" + name]["post"]
    schema = op["requestBody"]["content"]["application/json"]["schema"]
    body = {}
    for field, prop in schema.get("properties", {}).items():
        leaf = {"type": prop.get("type", "string")}
        if field == "customer_id":
            leaf["default"] = "{{customer_id}}"
        else:
            placeholder = field if field not in OWN_VARS else name + "_" + field
            leaf["default"] = "{{" + placeholder + "}}"
            leaf["description"] = prop.get("description", field)
            if prop.get("enum"):
                leaf["enum"] = prop["enum"]; leaf["description"] += " One of: " + ", ".join(prop["enum"]) + "."
        body[field] = leaf
    if lifecycle:
        body["outcome"]["default"], body["reason"]["default"] = "{{outcome}}", "{{reason}}"
    t = {"type": "function", "config": {"timeoutMs": 12000, "maxRetries": retries},
         "function": {"name": name, "handler": "__function__:api_call", "description": descriptions.get(name, op.get("summary", name)),
                      "parameters": {"type": "object", "properties": {
                          "url": {"type": "string", "default": base + "/" + name}, "method": {"type": "string", "default": "POST"},
                          "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                          "body": {"type": "object", "properties": body, "required": [f for f in schema.get("required", []) if f != "customer_id"]}}}}}
    if lifecycle:
        t["config"]["alwaysRunsAt"] = [lifecycle]
    if mapping:
        t["response_mapping"] = mapping
    if (name, "pre") in hook_map:
        t["pre_process_code"] = hook_map[(name, "pre")]
    if (name, "post") in hook_map:
        t["post_process_code"] = hook_map[(name, "post")]
    return t


def prepare_code(policy):
    o = policy.get("outcomes", {}).get("unclear", {})
    return DATES_SRC + "\nimport json\nPOLICY = " + lit({k: policy.get(k, {}) for k in ("calendar", "bands", "callback")}) + "\n" + (
        "try:\n    for k, v in calendar_facts(vars.get('now'), POLICY).items():\n        vars[k] = v\nexcept Exception:\n    pass\n"
        "for k, v in [('product_facts_json', '[]'), ('promises_recorded', '[]'), ('notes_recorded', '[]'), ('promise_failures', '0'), ('id_state', 'pending'),\n"
        "             ('transfer_state', 'none'), ('callback_state', 'none'), ('promise_state', 'none'), ('debt_summary', 'not loaded yet'), ('product_count', '0'),\n"
        "             ('outcome', " + json.dumps(str(o.get("outcome", ""))) + "), ('reason', " + json.dumps(str(o.get("reason", ""))) + ")]:\n    vars[k] = v\n")


def account_code(policy):
    o = policy.get("outcomes", {}).get("refused", {})
    return DATES_SRC + "\nimport json" + HELPERS + "POLICY = " + lit({k: policy.get(k, {}) for k in ("calendar", "bands", "floor_field", "product_words")}) + "\n" + (
        "try:\n    products = _load('products', None)\n    if products is None:\n        products = _load('account_response.data.products', [])\n"
        "    r = product_facts(products, POLICY, vars.get('now'))\n    vars['product_facts_json'] = json.dumps(r['facts'])\n"
        "    vars['debt_summary'] = r['summary'] or 'No product information was returned by the account service.'\n    vars['product_count'] = str(r['count'])\n"
        "    vars['account_state'] = 'ok' if r['count'] else 'empty'\nexcept Exception:\n    vars['account_state'] = 'error'\n"
        "vars['outcome'] = " + json.dumps(str(o.get("outcome", ""))) + "\nvars['reason'] = " + json.dumps(str(o.get("reason", ""))) + "\n")


def outcome_code(policy):
    note_sit = {v: k for k, v in policy.get("note_reasons", {}).items()}
    return "import json" + HELPERS + "OUT = " + lit(policy.get("outcomes", {})) + "\nQUEUES = " + lit(policy.get("queues", {})) + "\nNOTE_SIT = " + lit(note_sit) + "\n" + (
        "try:\n    promises, notes = _load('promises_recorded', []), _load('notes_recorded', [])\n"
        "    if vars.get('transfer_state') == 'done':\n        q = str(vars.get('transfer_queue') or '')\n"
        "        sit = next(('transfer_' + k for k, v in QUEUES.items() if str(v) == q), 'transfer_human')\n"
        "    elif promises:\n        sit = 'promise'\n"
        "    elif notes:\n        order = [str(f.get('product_id')) for f in _load('product_facts_json', [])]\n"
        "        notes.sort(key=lambda n: order.index(str(n.get('product_id'))) if str(n.get('product_id')) in order else 99)\n"
        "        reasons = [NOTE_SIT.get(str(n.get('reason')), 'refused') for n in notes]\n"
        "        sit = 'paid' if all(r == 'paid' for r in reasons) else next((r for r in reasons if r != 'paid'), 'refused')\n"
        "    else:\n        sit = str(vars.get('end_reason') or 'none')\n"
        "        if sit == 'none' and int(float(vars.get('promise_failures') or 0)) >= 2:\n            sit = 'service_error'\n"
        "        if sit not in OUT:\n            sit = 'refused'\n"
        "    o = OUT.get(sit) or OUT.get('refused') or dict()\n    vars['outcome'] = str(o.get('outcome', ''))\n    vars['reason'] = str(o.get('reason', ''))\nexcept Exception:\n    pass\n")


def fixed_outcome_code(policy, situation):
    o = policy.get("outcomes", {}).get(situation, {})
    return "vars['outcome'] = " + json.dumps(str(o.get("outcome", ""))) + "\nvars['reason'] = " + json.dumps(str(o.get("reason", ""))) + "\n"


def render(policy, spec):
    hook_map, desc = hooks.all_hooks(policy), prompts.tool_descriptions(policy)
    goodbye = policy.get("goodbye", "Thank you. Goodbye.")
    multi = policy.get("multi_product", {}).get("enabled")
    T = lambda name, **kw: tool(spec, name, hook_map, desc, **kw)
    nodes = {}
    nodes["prepare"] = code_node("prepare", prepare_code(policy), "opening")
    nodes["opening"] = {"name": "opening", "node_type": "conversation", "task_message": prompts.opening_task(policy),
        "on_enter": {"type": "tts", "text": policy.get("opening_sentence", "") + " " + policy.get("confirm_question", "").replace("{title}", "{{title}}").replace("{last_name}", "{{last_name}}")},
        "on_enter_first_entry_only": True, "max_node_turns": 6, "max_turn_transition": "outcome_unclear",
        "extraction_schema": [extraction("who", ["customer", "other_person", "wrong_number", "deceased", "unclear"], "Who is on the line. customer only if they clearly confirmed being the customer (yes, that's me, speaking, their own name). other_person if someone else answered or the customer is not available. wrong_number if the number does not belong to the customer. deceased if the customer has died. unclear otherwise."),
                              extraction("confirm_failed_twice", ["yes", "no"], "yes only when the assistant has asked twice whether it is speaking with the customer and the latest answer is still not a clear confirmation.")],
        "transitions": [when("mark_confirmed", "the customer confirmed", ("who", "customer")), when("third_party", "someone else answered", ("who", "other_person")),
                        when("outcome_wrong_number", "wrong number", ("who", "wrong_number")), when("outcome_deceased", "customer has died", ("who", "deceased")),
                        when("outcome_unclear", "unclear after two asks", ("confirm_failed_twice", "yes")), always("opening")]}
    nodes["third_party"] = {"name": "third_party", "node_type": "conversation", "task_message": prompts.third_party_task(policy), "max_node_turns": 10, "max_turn_transition": "outcome_no_callback",
        "tools": [T("schedule_callback")],
        "extraction_schema": [extraction("third_party_result", ["none", "no_callback", "wrong_number", "deceased"], "no_callback only when the person has twice given a day or time outside the allowed window or refuses any callback. wrong_number if the number does not belong to the customer. deceased if the customer has died. none otherwise.")],
        "transitions": [when("outcome_callback", "callback booked", ("callback_state", "done")), when("outcome_no_callback", "no callback possible", ("third_party_result", "no_callback")),
                        when("outcome_wrong_number", "wrong number", ("third_party_result", "wrong_number")), when("outcome_deceased", "customer has died", ("third_party_result", "deceased")), always("third_party")]}
    nodes["mark_confirmed"] = code_node("mark_confirmed", fixed_outcome_code(policy, "id_declined"), "identity")
    nodes["identity"] = {"name": "identity", "node_type": "conversation", "task_message": prompts.identity_task(policy), "max_node_turns": 14, "max_turn_transition": "outcome_id_declined",
        "tools": [T("verify_identity", mapping=[{"path": "data.all_verified", "variable": "id_all_verified"}]), T("transfer_to_agent")],
        "extraction_schema": [extraction("identity_signal", ["none", "declined"], "declined only when the customer has refused the security questions a second time, or has twice asked what the call is about instead of answering, or has said twice that they do not want to talk. none otherwise.")],
        "transitions": [when("account", "all security questions passed", ("id_state", "verified"), ("id_all_verified", "true"), ("verify_identity_response.data.all_verified", "true")),
                        when("outcome_id_failed", "too many wrong answers", ("id_state", "failed")), when("set_outcome", "transferred to a person", ("transfer_state", "done")),
                        when("outcome_id_declined", "customer declined the check", ("identity_signal", "declined")), always("identity")]}
    nodes["account"] = {"name": "account", "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "account_facts", "on_enter": {"type": "silent"},
        "disable_inactivity_monitor": True, "suppress_tool_results": True, "pre_actions": [T("get_account", retries=2)],
        "response_mapping": [{"path": "data.products", "variable": "products"}], "transitions": [always("account_facts")]}
    nodes["account_facts"] = code_node("account_facts", account_code(policy), "negotiate")
    tools = [T("create_promise"), T("transfer_to_agent")] + ([T("add_note")] if multi else [])
    nodes["negotiate"] = {"name": "negotiate", "node_type": "conversation", "task_message": prompts.negotiate_task(policy), "max_node_turns": 60, "max_turn_transition": "set_outcome", "tools": tools,
        "extraction_schema": [extraction("end_reason", ["none", "paid", "dispute", "hardship", "refused", "service_error"], "Why the call is ending without a promise, if it is. paid: the customer says the amount is already paid. dispute: the customer says the debt or product is not theirs or was closed. hardship: illness, bereavement or job loss and no promise. refused: the customer refuses or will not talk. service_error: recording failed twice. none while the conversation continues or a promise was recorded."),
                              extraction("conversation_done", ["yes", "no"], "yes only after the assistant has said goodbye.")],
        "transitions": [when("set_outcome", "transferred to a person", ("transfer_state", "done")),
                        {"target_node": "set_outcome_quiet", "description": "The assistant has said goodbye and the call is complete", "is_tool_call": True, "condition": {"operator": "matches_intent", "description": "The conversation is complete and the assistant has said goodbye"}},
                        when("set_outcome_quiet", "goodbye said", ("conversation_done", "yes")), always("negotiate")]}
    nodes["set_outcome"] = code_node("set_outcome", outcome_code(policy), "end_goodbye")
    nodes["set_outcome_quiet"] = code_node("set_outcome_quiet", outcome_code(policy), "end_quiet")
    ends = {"unclear": "end_goodbye", "callback": "end_goodbye", "no_callback": "end_goodbye", "wrong_number": "end_goodbye", "deceased": "end_deceased", "id_failed": "end_id_failed", "id_declined": "end_goodbye"}
    for sit, end in ends.items():
        nodes["outcome_" + sit] = code_node("outcome_" + sit, fixed_outcome_code(policy, sit), end)
    nodes["end_goodbye"] = end_node("end_goodbye", goodbye)
    nodes["end_quiet"] = end_node("end_quiet", "")
    nodes["end_deceased"] = end_node("end_deceased", (policy.get("third_party", {}).get("deceased_sentence", "") + " " + goodbye).strip())
    nodes["end_id_failed"] = end_node("end_id_failed", (policy.get("identity", {}).get("on_fail_sentence", "") + " " + goodbye).strip())
    return {"initial_node": "prepare", "system_prompt": prompts.system_prompt(policy), "nodes": nodes, "global_nodes": {},
            "tools": [T("close_call", lifecycle="end_of_call")]}
