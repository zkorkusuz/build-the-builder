"""Render a Freya workflow from a policy and the bank's tool API file. Pure: no network."""
import json, pathlib
from builder.fields import deref, field_names, find_path
from builder import dates, hooks, prompts

DATES_SRC = pathlib.Path(dates.__file__).read_text()
# Variables the workflow sets itself. A model-filled tool field must not share one of these names.
OWN_VARS = {"today", "now", "outcome", "reason", "products", "debt_summary", "debt_statement", "product_count", "id_state", "transfer_state",
            "callback_state", "promise_state", "end_reason", "who", "identity_signal", "third_party_result", "conversation_done"}
COLUMNS = ["prepare", "opening opening_again", "third_party_prep mark_confirmed", "third_party identity", "account", "account_facts", "negotiate", "count_refusal offer_deadline resolve_proposal set_outcome stop_offers wrap_up wrap_up_ outcome_", "end_", "close", "hang_up_"]


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
    fn = {"type": "function", "config": {"timeoutMs": 12000, "maxRetries": 2},      # the sandbox service drops a connection now and then; a code step never raises on its own
          "function": {"name": "code_exec", "handler": "__function__:code_exec",
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


def tool(spec, name, hook_map, descriptions, fields, mapping=None, retries=0, lifecycle=None):
    """An api_call tool for one path of the OpenAPI file. customer_id is baked; other fields are model-filled."""
    base = (spec.get("servers") or [{}])[0].get("url", "").rstrip("/")
    path, op = find_path(spec, name)
    schema = deref(spec, (((op.get("requestBody") or {}).get("content") or {}).get("application/json") or {}).get("schema") or {})
    body = {}
    for field, prop in schema.get("properties", {}).items():
        prop = deref(spec, prop)
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
    if name == "close_call":
        for role in ("outcome", "reason"):                      # the outcome lives in vars, set by the outcome code steps
            if fields[name].get(role) in body:
                body[fields[name][role]]["default"] = "{{" + role + "}}"
    t = {"type": "function", "config": {"timeoutMs": 12000, "maxRetries": retries},
         "function": {"name": name, "handler": "__function__:api_call", "description": descriptions.get(name, op.get("summary", name)),
                      "parameters": {"type": "object", "properties": {
                          "url": {"type": "string", "default": base + path}, "method": {"type": "string", "default": "POST"},
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


def default_outcome(policy, situation):
    """The (outcome, reason) a phase falls back to if the call drops there: a fixed situation, or an end reason key."""
    o = (policy.get("outcomes") or {}).get(situation)
    if o is None:
        ends = policy.get("end_reasons") or []
        o = next((e for e in ends if e.get("key") == situation), ends[0] if ends else {})
    return o


def facts_code(policy, situation, extra=""):
    """Calendar facts plus the default outcome for the phase that follows. Runs in several code steps so the facts exist even when the first step is skipped."""
    o = default_outcome(policy, situation)
    pol = {k: policy.get(k) or {} for k in ("calendar", "bands", "callback", "attempt1_rule")}
    return DATES_SRC + "\nimport json" + hooks.COMMON + "POLICY = " + hooks.literal(pol) + "\n" + (
        "try:\n    for k, v in calendar_facts(vars.get('now'), POLICY).items():\n        vars[k] = v\nexcept Exception:\n    pass\n"
        "for k, v in [('product_facts_json', '[]'), ('promises_recorded', '[]'), ('notes_recorded', '[]'), ('promise_failures', '0'), ('id_state', 'pending'), ('offer_now', 'none'), ('proposed_day_words', ''),\n"
        "             ('transfer_state', 'none'), ('callback_state', 'none'), ('promise_state', 'none'), ('debt_summary', 'not loaded yet'), ('debt_statement', ''), ('product_count', '0')]:\n"
        "    if not vars.get(k):\n        vars[k] = v\n"
        "vars['outcome'] = " + json.dumps(str(o.get("outcome", ""))) + "\nvars['reason'] = " + json.dumps(str(o.get("reason", ""))) + "\n" + extra)


def account_code(policy, fields):
    s, m = policy.get("sentences") or {}, policy.get("multi_product") or {}
    pol = {k: policy.get(k) or {} for k in ("calendar", "bands", "floor_field", "product_words", "attempt1_rule")}
    pol["fields"], products = fields, "account_response.data." + fields["products"]
    first = str(s.get("first_ask") or "")
    first_multi = str((s.get("first_ask_multi") if m.get("enabled") else "") or first)      # the question for several products, chosen per call by the count
    return "P2 = " + hooks.literal(pol) + "\nINTRO = " + json.dumps(str(policy.get("debt_intro_sentence") or "")) + "\nFIRST = " + json.dumps(first) + "\nFIRST_MULTI = " + json.dumps(first_multi) + "\n" + (
        "def _flat_list(prefix):\n    rows = dict()\n    try:\n        for k in list(vars.keys()):\n            if str(k).startswith(prefix):\n                rest = str(k)[len(prefix):].split('.')\n"
        "                if len(rest) == 2 and rest[0].isdigit():\n                    rows.setdefault(int(rest[0]), dict())[rest[1]] = vars.get(k)\n    except Exception:\n        pass\n    return [rows[i] for i in sorted(rows)]\n"
        "try:\n    products = _load('products', None) or _flat_list(" + json.dumps(products + ".") + ") or _load(" + json.dumps(products) + ", [])\n"
        "    r = product_facts(products, P2, vars.get('now'))\n    vars['product_facts_json'] = json.dumps(r['facts'])\n"
        "    vars['debt_summary'] = r['summary'] or 'No product information was returned by the account service.'\n    vars['product_count'] = str(r['count'])\n"
        "    vars['debt_statement'] = ' '.join(x for x in [INTRO, r['spoken'], FIRST_MULTI if r['count'] > 1 else FIRST] if x)\n"
        "    vars['attempts_allowed'] = str(r['facts'][0]['attempts']) if r['count'] == 1 else 'per_product'\n"
        "    vars['account_state'] = 'ok' if r['count'] else 'empty'\nexcept Exception:\n    vars['account_state'] = 'error'\n")


def outcome_code(policy):
    ends = {str(e.get("key")): e for e in policy.get("end_reasons") or []}
    note_key = {str(e.get("note_reason")): k for k, e in ends.items() if e.get("note_reason")}
    return "import json" + hooks.COMMON + "OUT = " + hooks.literal(policy.get("outcomes") or {}) + "\nTRANSFERS = " + hooks.literal(policy.get("transfers") or []) + "\nENDS = " + hooks.literal(ends) + "\nNOTE_KEY = " + hooks.literal(note_key) + "\n" + (
        "try:\n    promises, notes = _load('promises_recorded', []), _load('notes_recorded', [])\n    keys = list(ENDS.keys())\n"
        "    default = 'refused' if 'refused' in ENDS else (keys[0] if keys else '')\n    o = None\n"
        "    if vars.get('transfer_state') == 'done':\n        q = str(vars.get('transfer_queue') or '')\n"
        "        o = next((t for t in TRANSFERS if str(t.get('queue')) == q), TRANSFERS[0] if TRANSFERS else None)\n"
        "    elif promises:\n        o = OUT.get('promise')\n"
        "    elif notes:\n        order = [str(f.get('product_id')) for f in _load('product_facts_json', [])]\n"
        "        notes.sort(key=lambda n: order.index(str(n.get('product_id'))) if str(n.get('product_id')) in order else 99)\n"
        "        ks = [NOTE_KEY.get(str(n.get('reason')), default) for n in notes]\n"
        "        key = 'paid' if ('paid' in ENDS and all(k == 'paid' for k in ks)) else next((k for k in ks if k != 'paid'), default)\n        o = ENDS.get(key)\n"
        "    else:\n        key = str(vars.get('end_reason') or 'none')\n"
        "        if key == 'none' and int(float(vars.get('promise_failures') or 0)) >= 2 and 'service_error' in ENDS:\n            key = 'service_error'\n"
        "        o = ENDS.get(key) or ENDS.get(default)\n"
        "    o = o or dict()\n    vars['outcome'] = str(o.get('outcome', ''))\n    vars['reason'] = str(o.get('reason', ''))\nexcept Exception:\n    pass\n")


def fixed_outcome_code(policy, situation):
    o = (policy.get("outcomes") or {}).get(situation) or {}
    return "vars['outcome'] = " + json.dumps(str(o.get("outcome", ""))) + "\nvars['reason'] = " + json.dumps(str(o.get("reason", ""))) + "\n"


def positions(nodes):
    """A layered layout for the dashboard: one column per stage, rows within it."""
    rows = {}
    for name, node in nodes.items():
        col = next((i for i, c in enumerate(COLUMNS) if any(name == k or (k.endswith("_") and name.startswith(k)) for k in c.split())), len(COLUMNS))
        node["position"] = {"x": col * 430, "y": rows.get(col, 0) * 240}
        rows[col] = rows.get(col, 0) + 1


def goodbye_transition(target, description):
    """A transition the dialogue model triggers itself, after it has said goodbye."""
    return {"target_node": target, "description": description, "is_tool_call": True, "condition": {"operator": "matches_intent", "description": description}}


def render(policy, spec):
    recompute = "if str(vars.get('id_state') or '') == 'verified':\n" + "".join("    " + line + "\n" for line in outcome_code(policy).splitlines())
    fields = field_names(policy, spec)
    hook_map, desc = hooks.all_hooks(policy, recompute, DATES_SRC, fields), prompts.tool_descriptions(policy, fields)
    goodbye = str(policy.get("goodbye") or "Thank you. Goodbye.")
    multi = (policy.get("multi_product") or {}).get("enabled")
    ends = policy.get("end_reasons") or []
    T = lambda name, **kw: tool(spec, name, hook_map, desc, fields, **kw)
    FV, FA = fields["verify_identity"], fields["get_account"]
    nodes = {}
    nodes["prepare"] = code_node("prepare", facts_code(policy, "unclear"), "opening")
    c = policy.get("confirmation") or {}
    q = prompts.call_vars(policy.get("confirm_question"))
    who = extraction("who", ["customer", "other_person", "wrong_number", "deceased", "unclear"], "Who is on the line. customer only if they clearly confirmed being the customer (yes, that's me, speaking, their own name). other_person if someone else answered or the customer is not available. wrong_number if the number does not belong to the customer. deceased if the customer has died. unclear otherwise.")
    routes = lambda: [when("mark_confirmed", "the customer confirmed", ("who", "customer")), when("third_party_prep", "someone else answered", ("who", "other_person")),
                      when("outcome_wrong_number", "wrong number", ("who", "wrong_number")), when("outcome_deceased", "customer has died", ("who", "deceased"))]
    asks = max(int(c.get("max_asks") or 2), 1)
    nodes["opening"] = {"name": "opening", "node_type": "conversation", "extraction_schema": [who], "task_message": prompts.opening_task(policy),
        "on_enter": {"type": "tts", "text": (str(policy.get("opening_sentence") or "") + " " + q).strip()}, "on_enter_first_entry_only": True,
        "transitions": routes() + ([always("opening_again")] if asks > 1 else [goodbye_transition("outcome_unclear_quiet", "The person could not be confirmed and the assistant has said goodbye")])}
    if asks == 1:
        nodes["opening"]["max_node_turns"], nodes["opening"]["max_turn_transition"] = 2, "outcome_unclear"
        nodes["opening"]["task_message"] += "\nOnly one ask is allowed: if the reply is not a clear confirmation, say thank you and goodbye, and in the same message call transition_to_outcome_unclear_quiet."
    else:
        # The reply that enters this step counts as its first turn, and the cap fires before the step's transitions once turns exceed it:
        # a cap equal to the allowed asks lets the reply to the last ask route (confirmed, someone else, ...) and ends the call on the one after.
        more = asks - 2
        confirmed_now = extraction("confirmed_now", ["yes", "no"], "yes if this latest reply confirms that the person is the customer (yes, that's me, speaking, their own name, or any clear agreement). no otherwise.")
        confirmed_now["min_confidence"] = 0.5
        nodes["opening_again"] = {"name": "opening_again", "node_type": "conversation", "extraction_schema": [who, confirmed_now], "max_node_turns": asks, "max_turn_transition": "outcome_unclear",
            "on_enter": {"type": "llm", "prompt": "The person has not clearly confirmed being the customer. If they asked a question, answer it in one short sentence without saying why you are calling. Then ask exactly: \"" + q + "\". Do not say goodbye and say nothing else."},
            "on_enter_first_entry_only": True,
            "task_message": ("You have just asked again whether you are speaking with the customer, {{title}} {{last_name}}.\n"
                             + ("You may ask " + str(more) + " more time(s) if the reply is unclear; after that, if the reply is not a clear confirmation (" + ", ".join(c.get("accepted") or ["yes"]) + "), say thank you and goodbye, and in the same message call transition_to_outcome_unclear_quiet. Never say goodbye without calling it.\n"
                                if more > 0 else "No further ask is allowed: a reply that is not a clear confirmation ends the call for you.\n")
                             + "Do not say why you are calling. If the person says the customer is not available, is someone else, the number is wrong, or the customer has died, say nothing more; the next step is handled for you."),
            "transitions": routes() + [when("mark_confirmed", "the customer confirmed", ("confirmed_now", "yes"))]
                           + ([always("outcome_unclear")] if more == 0 else [goodbye_transition("outcome_unclear_quiet", "The person could not be confirmed after the allowed asks and the assistant has said goodbye")])}
    nodes["third_party_prep"] = code_node("third_party_prep", facts_code(policy, "no_callback"), "third_party")
    nodes["third_party"] = {"name": "third_party", "node_type": "conversation", "task_message": prompts.third_party_task(policy), "max_node_turns": 6, "max_turn_transition": "outcome_no_callback",
        "tools": [T("schedule_callback")],
        "extraction_schema": [extraction("third_party_result", ["none", "no_callback", "wrong_number", "deceased"], "no_callback only when, under the bank's rules, no callback can be booked and the assistant has stopped asking, or the person refuses any callback. wrong_number if the number does not belong to the customer. deceased if the customer has died. none otherwise.")],
        "transitions": [when("outcome_callback", "callback booked", ("callback_state", "done")), when("outcome_no_callback", "no callback possible", ("third_party_result", "no_callback")),
                        when("outcome_wrong_number", "wrong number", ("third_party_result", "wrong_number")), when("outcome_deceased", "customer has died", ("third_party_result", "deceased")),
                        goodbye_transition("outcome_no_callback_quiet", "No callback could be booked and the assistant has said goodbye")]}
    nodes["mark_confirmed"] = code_node("mark_confirmed", facts_code(policy, "id_declined"), "identity")
    nodes["identity"] = {"name": "identity", "node_type": "conversation", "task_message": prompts.identity_task(policy), "max_node_turns": 14, "max_turn_transition": "outcome_id_declined",
        "tools": [T("verify_identity", mapping=[{"path": "data." + FV["all_verified"], "variable": "id_all_verified"}])] + ([T("transfer_to_agent")] if policy.get("transfers") else []),
        "extraction_schema": [extraction("identity_signal", ["none", "wants_person", "declined"], "wants_person when the customer asks for a human, a person, an agent or a transfer, however often. declined only when the customer has refused the security questions a second time, or has twice asked what the call is about instead of answering, or has said twice that they do not want to talk, and has not asked for a person. none otherwise.")],
        "transitions": [when("account", "all security questions passed", ("id_state", "verified"), ("id_all_verified", "true"), ("verify_identity_response.data." + FV["all_verified"], "true")),
                        when("outcome_id_failed", "too many wrong answers", ("id_state", "failed")), when("set_outcome", "transferred to a person", ("transfer_state", "done")),
                        when("outcome_id_declined", "customer declined the check", ("identity_signal", "declined")),
                        goodbye_transition("outcome_id_declined_quiet", "The customer will not answer the security questions and the assistant has said goodbye")]}
    nodes["account"] = {"name": "account", "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "account_facts", "on_enter": {"type": "silent"},
        "disable_inactivity_monitor": True, "suppress_tool_results": True, "pre_actions": [T("get_account", retries=2)],
        "response_mapping": [{"path": "data." + FA["products"], "variable": "products"}], "transitions": [always("account_facts")]}
    nodes["account_facts"] = code_node("account_facts", facts_code(policy, "refused", account_code(policy, FA)), "negotiate")
    tools = [T("create_promise")] + ([T("transfer_to_agent")] if policy.get("transfers") else []) + ([T("add_note")] if multi else [])
    keys = ["none"] + [str(e.get("key")) for e in ends]
    meanings = " ".join(str(e.get("key")) + ": " + str(e.get("meaning", "")) for e in ends)
    # The extractor only classifies the latest reply; a code step counts refusals against the attempts allowed and ends the call when they are used up.
    stops = [{"target_node": "count_refusal", "description": "the customer refused", "condition": {"logic": "or", "conditions": [{"logic": "and", "conditions": [
                {"variable": "last_reply", "operator": "equals", "operand": "refusal"}]}]}},
             {"target_node": "offer_deadline", "description": "no exact day after being asked", "condition": {"logic": "or", "conditions": [{"logic": "and", "conditions": [
                {"variable": "product_count", "operator": "equals", "operand": "1"}, {"variable": "last_reply", "operator": "equals", "operand": "no_exact_day"}]}]}},
             {"target_node": "resolve_proposal", "description": "the customer named a day", "condition": {"logic": "or", "conditions": [{"logic": "and", "conditions": [
                {"variable": "last_reply", "operator": "equals", "operand": "proposal"}, {"variable": "proposed_day_words", "operator": "is_set"}]}]}}]
    nodes["negotiate"] = {"name": "negotiate", "node_type": "conversation", "task_message": prompts.negotiate_task(policy), "max_node_turns": 60, "max_turn_transition": "set_outcome", "tools": tools,
        "on_enter": {"type": "tts", "text": "{{debt_statement}}"}, "on_enter_first_entry_only": True,
        "extraction_schema": [extraction("end_reason", keys, "Why the call is ending without a promise, if it is. " + meanings + " none while the conversation continues or a promise was recorded."),
                              extraction("conversation_done", ["yes", "no"], "yes only after the assistant has said goodbye."),
                              {"name": "proposed_day_words", "type": "string", "min_confidence": 0.5, "description": "The customer's own words for the day they propose or accept, exactly as said (for example next Friday, Monday the 19th, tomorrow, 20 November). If the customer gave the day in parts over the last two messages, join the parts. Leave out any time of day. Empty if no day is named."},
                              extraction("last_reply", ["refusal", "proposal", "no_exact_day", "question", "hardship", "other"], "What the customer's latest message is. refusal: a no to paying with no date and no amount of their own, or a refusal of the date or amount the assistant just proposed. proposal: the customer offers a date or an amount, or accepts one. no_exact_day: the assistant asked for the exact day and the customer still names none (does not know, will see, when the salary comes). hardship: illness, a death in the family or job loss. question: asks something. other: anything else.")],
        "transitions": stops + [when("set_outcome", "transferred to a person", ("transfer_state", "done")),
                        goodbye_transition("wrap_up", "A promise was recorded or the customer was transferred, and the assistant has said goodbye")]
                       + [goodbye_transition("wrap_up_" + str(e.get("key")), "The call ends without a promise because " + str(e.get("meaning", "")) + ", and the assistant has said goodbye") for e in ends]
                       + [
                        when("wrap_up", "goodbye said", ("conversation_done", "yes"))]}
    nodes["set_outcome"] = code_node("set_outcome", outcome_code(policy), "end_goodbye")
    # a reason the extractor already found (hardship, dispute, paid) outranks a refusal, as the brief's special rules come before persuasion
    nodes["stop_offers"] = code_node("stop_offers", "if str(vars.get('end_reason') or 'none') in ('none', ''):\n    vars['end_reason'] = 'refused'\n" + outcome_code(policy), "end_goodbye")
    nodes["offer_deadline"] = code_node("offer_deadline", (
        "import json\ntry:\n    facts = json.loads(vars.get('product_facts_json') or '[]')\n    f = facts[0] if facts else dict()\n"
        "    if json.loads(vars.get('promises_recorded') or '[]'):\n        raise ValueError('a promise exists')\n"
        "    vars['offer_now'] = 'The customer gave no exact day: propose exactly ' + str(f.get('deadline')) + ', the latest allowed date, for the amount in play, and read it back if accepted. Do not propose any other date.'\n"
        "    vars['last_reply'] = 'other'\nexcept Exception:\n    vars['offer_now'] = ''\n"), "negotiate")
    nodes["resolve_proposal"] = code_node("resolve_proposal", DATES_SRC + "\nimport json\nADJ = " + hooks.literal(policy.get("date_adjust") or {}) + "\nCAL = " + hooks.literal(policy.get("calendar") or {}) + "\n" + (
        "try:\n    words = str(vars.get('proposed_day_words') or '')\n    vars['proposed_day_words'] = ''\n    vars['last_reply'] = 'other'\n"
        "    facts = json.loads(vars.get('product_facts_json') or '[]')\n    today = datetime.date.fromisoformat(str(vars.get('today'))[:10])\n"
        "    day = parse_day_words(words, today) if words else None\n"
        "    if day is not None and len(facts) > 1 and not json.loads(vars.get('promises_recorded') or '[]'):\n"
        "        parts = []\n        for f in facts:\n            dl = datetime.date.fromisoformat(str(f.get('deadline'))[:10])\n            use, why = adjust_day(day, today, dl, CAL, ADJ)\n            use = use or dl\n"
        "            parts.append(str(f.get('words')) + ' (id ' + str(f.get('product_id')) + '): ' + use.isoformat() + ((', its latest allowed date, because the named day ' + why.split(';')[0]) if why else ''))\n"
        "        vars['offer_now'] = 'The customer said ' + json.dumps(words) + ', which is ' + say(day) + '. Record these dates: ' + '; '.join(parts) + '. Read all of them back together with these exact dates, ask for one confirmation, then CALL create_promise once per product with exactly these dates; do not compute any date yourself.'\n"
        "    elif day is not None and facts and not json.loads(vars.get('promises_recorded') or '[]'):\n"
        "        deadline = datetime.date.fromisoformat(str(facts[0].get('deadline'))[:10])\n        use, why = adjust_day(day, today, deadline, CAL, ADJ)\n"
        "        if why and use is not None:\n            vars['offer_now'] = 'The customer said ' + json.dumps(words) + ', which is ' + say(day) + '; it ' + why + '. Read back ' + say(use) + ' and record exactly ' + use.isoformat() + ' once confirmed.'\n"
        "        elif why:\n            vars['offer_now'] = 'The customer said ' + json.dumps(words) + ', which is ' + say(day) + '; it ' + why + '.'\n"
        "        else:\n            vars['offer_now'] = 'The customer said ' + json.dumps(words) + ', which is ' + say(day) + '. Read back exactly this date and record ' + day.isoformat() + ' once confirmed; do not compute the date yourself.'\n"
        "except Exception:\n    pass\n"), "negotiate")
    refused_note = next((e.get("note_reason") for e in ends if e.get("key") == "refused" and e.get("note_reason")), "refused")
    # with several products the refusals are counted per product; the product's first offer is already attempt 1 (no today question again), so refusal n ends it when n reaches its attempts
    nodes["count_refusal"] = code_node("count_refusal", "import json\nNOTE_REFUSED = " + json.dumps(str(refused_note)) + "\n" + (
        "try:\n    facts = json.loads(vars.get('product_facts_json') or '[]')\n    vars['last_reply'] = 'other'\n    vars['offer_now'] = ''\n"
        "    if len(facts) > 1:\n"
        "        handled = [str(x.get('product_id')) for x in json.loads(vars.get('promises_recorded') or '[]') + json.loads(vars.get('notes_recorded') or '[]')] + [str(x) for x in json.loads(vars.get('service_error_products') or '[]')]\n"
        "        cur = next((f for f in facts if str(f.get('product_id')) not in handled), None)\n        vars['refusals_over'] = 'no'\n"
        "        if cur is not None:\n            key = 'refusals_' + str(cur.get('product_id'))\n            n = int(float(vars.get(key) or 0)) + 1\n            vars[key] = str(n)\n            allowed = int(float(cur.get('attempts') or 0))\n"
        "            if n >= allowed:\n                vars['offer_now'] = 'The persuasion attempts for ' + str(cur.get('words')) + ' (id ' + str(cur.get('product_id')) + ') are used up: make no further offer for it. CALL add_note with that product_id and reason ' + json.dumps(NOTE_REFUSED) + ', then continue with the next product that has no promise and no note, starting at its own attempt 1; if none is left, thank the customer, say goodbye and call transition_to_wrap_up.'\n"
        "            else:\n                vars['offer_now'] = 'Refusal ' + str(n) + ' for ' + str(cur.get('words')) + ' (id ' + str(cur.get('product_id')) + '): make persuasion attempt ' + str(n + 1) + ' of ' + str(allowed) + ' exactly as its product line in your facts says, for this product only; do not ask about today again.'\n"
        "    else:\n        n = int(float(vars.get('refusals') or 0)) + 1\n        vars['refusals'] = str(n)\n"
        "        allowed = int(float(vars.get('attempts_allowed') or 99))\n        vars['refusals_over'] = 'yes' if n > allowed else 'no'\nexcept Exception:\n    vars['refusals_over'] = 'no'\n"),
        "negotiate", before=[when("stop_offers", "persuasion attempts used up", ("refusals_over", "yes"))])
    nodes["wrap_up"] = code_node("wrap_up", outcome_code(policy), "end_quiet")
    for e in ends:
        key = str(e.get("key"))
        nodes["wrap_up_" + key] = code_node("wrap_up_" + key, "vars['end_reason'] = " + json.dumps(key) + "\n" + outcome_code(policy), "end_quiet")
    for sit, end in {"unclear": "end_goodbye", "callback": "end_goodbye", "no_callback": "end_goodbye", "wrong_number": "end_goodbye", "deceased": "end_deceased", "id_failed": "end_id_failed", "id_declined": "end_goodbye"}.items():
        nodes["outcome_" + sit] = code_node("outcome_" + sit, fixed_outcome_code(policy, sit), end)
    for sit in ("unclear", "no_callback", "id_declined"):
        nodes["outcome_" + sit + "_quiet"] = code_node("outcome_" + sit + "_quiet", fixed_outcome_code(policy, sit), "end_quiet")
    farewells = {"goodbye": goodbye, "quiet": "", "deceased": (str((policy.get("third_party") or {}).get("deceased_sentence") or "") + " " + goodbye).strip(),
                 "id_failed": (str((policy.get("identity") or {}).get("on_fail_sentence") or "") + " " + goodbye).strip()}
    # A fixed line is spoken only by a step that waits for the customer or by the hang-up terminal, so every exit path runs through
    # the silent close step and then a terminal that speaks the farewell: close_call is the last tool call and never depends on the
    # platform's post-call analysis, which sometimes never arrives. Model-driven exits say goodbye before reaching here.
    for kind in farewells:
        nodes["end_" + kind] = code_node("end_" + kind, "vars['farewell'] = " + json.dumps(kind) + "\n", "close")
    nodes["close"] = {"name": "close", "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "hang_up_goodbye", "disable_inactivity_monitor": True,
                      "on_enter": {"type": "silent"}, "suppress_tool_results": True, "pre_actions": [T("close_call", retries=2, lifecycle=None)],   # a sandbox fault on the close has no model to retry it
                      "transitions": [when("hang_up_" + kind, "farewell " + kind, ("farewell", kind)) for kind in farewells if kind != "goodbye"] + [always("hang_up_goodbye")]}
    for kind, spoken in farewells.items():
        nodes["hang_up_" + kind] = end_node("hang_up_" + kind, spoken)
    positions(nodes)
    return {"initial_node": "prepare", "system_prompt": prompts.system_prompt(policy), "nodes": nodes, "global_nodes": {}, "tools": []}
