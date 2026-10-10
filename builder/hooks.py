"""Python hooks that run on Freya around each tool call, as source strings filled from the policy.

Every hook is wrapped in try/except, reads and writes through `vars`, and never contains two braces in a row:
policy values are inserted as indented JSON with `__NAME__` placeholders, never with str.format.
"""
import json


def literal(value):
    """A JSON literal safe for a Freya code string: indented so that no two braces touch."""
    return json.dumps(value, indent=1).replace("}}", "} }").replace("{{", "{ {")


def fill(template, **values):
    for name, value in values.items():
        template = template.replace("__" + name.upper() + "__", literal(value) if not isinstance(value, str) else value)
    return template


COMMON = """
def _d(result):
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if isinstance(d, dict):
            return d
    return None
def _flag(x):
    return str(x).lower() == 'true'
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

VERIFY_POST = """import json
__COMMON__
try:
    d = _d(result)
    P = __IDENTITY__
    if d is not None:
        left = d.get('wrong_answers_left')
        if _flag(d.get('all_verified')):
            vars['id_state'] = 'verified'
            d['what_to_do_next'] = 'All security questions passed. Thank the customer; the identity check is complete.'
        elif str(d.get('hint') or '') == str(P.get('hint_value') or 'day_month_swapped'):
            d['what_to_do_next'] = P.get('hint_instruction') or 'The day and month may be swapped. Ask the customer to say the month as a word, then CALL verify_identity again with the same field. This retry is not a wrong answer.'
        elif not _flag(d.get('ok')):
            d['what_to_do_next'] = 'The answer could not be read in the required format (' + str(d.get('error') or '') + '). Ask the customer to repeat it, then CALL verify_identity again with the same field. This is not counted as a wrong answer.'
        elif _flag(d.get('verified')):
            d['what_to_do_next'] = 'Correct. Now ask the next security question in the order of your instructions and CALL verify_identity with its answer. If there is no next question, wait: the check is complete.'
        elif left is not None and int(float(left)) <= 0:
            vars['id_state'] = 'failed'
            d['what_to_do_next'] = 'The identity check has failed. Do not mention any account or debt. Tell the customer: ' + str(P.get('on_fail_sentence') or 'I cannot verify your identity. Please use the mobile app or visit a branch.') + ' Then thank them and say goodbye.'
        else:
            d['what_to_do_next'] = 'Wrong answer. ' + str(left) + ' wrong answers left in total. Ask the same question once more and CALL verify_identity again with the new answer.'
except Exception:
    pass
"""

PROMISE_PRE = """import json, datetime
__COMMON__
CAL = __CAL__
def _biz(day):
    return day.weekday() in CAL.get('business_weekdays', [0, 1, 2, 3, 4]) and day.isoformat() not in CAL.get('holidays', [])
try:
    b = config.get('body') if isinstance(config, dict) else None
    facts = _load('product_facts_json', [])
    if isinstance(b, dict) and facts:
        ids = [f.get('product_id') for f in facts]
        if b.get('product_id') not in ids and len(facts) == 1:
            b['product_id'] = ids[0]
        f = next((x for x in facts if x.get('product_id') == b.get('product_id')), None)
        today = datetime.date.fromisoformat(str(vars.get('today'))[:10])
        day = datetime.date.fromisoformat(str(b.get('date'))[:10])
        deadline = datetime.date.fromisoformat(str(f.get('deadline'))[:10]) if f else day
        note = ''
        if day < today:
            day, note = today, 'moved to today, the earliest date allowed'
        if day > deadline:
            day, note = deadline, 'moved to the latest date allowed, ' + deadline.isoformat()
        for _ in range(10):
            if _biz(day) or day >= deadline:
                break
            day += datetime.timedelta(days=1)
            note = 'moved to the next business day, ' + day.isoformat()
        b['date'] = day.isoformat()
        vars['promise_date_note'] = note
        vars['promise_attempt'] = json.dumps({'product_id': b.get('product_id'), 'amount': b.get('amount'), 'date': b.get('date'), 'words': (f or {}).get('words', '')})
except Exception:
    pass
"""

PROMISE_POST = """import json
__COMMON__
try:
    d = _d(result)
    attempt = _load('promise_attempt', {})
    done = _load('promises_recorded', [])
    sentence = __AFTER_PROMISE__
    if d is not None and _flag(d.get('ok')):
        done.append(attempt)
        vars['promises_recorded'] = json.dumps(done)
        vars['promise_failures'] = '0'
        vars['promise_state'] = 'recorded'
        note = str(vars.get('promise_date_note') or '')
        text = 'Recorded: ' + str(attempt.get('words') or 'the product') + ', ' + str(attempt.get('amount')) + ' on ' + str(attempt.get('date')) + '.'
        if note:
            text += ' The date was ' + note + '; tell the customer the recorded date.'
        text += ' Tell the customer the promise is recorded and then say exactly: ' + json.dumps(sentence) + '.'
        text += ' Then continue with any product that still has no promise, or thank the customer, say goodbye and call transition_to_wrap_up.'
        d['what_to_do_next'] = text
    else:
        n = int(float(vars.get('promise_failures') or 0)) + 1
        vars['promise_failures'] = str(n)
        vars['promise_state'] = 'failed'
        if d is None:
            result['data'] = d = dict()
        if n < 2:
            d['what_to_do_next'] = 'NOT recorded: the service failed. Tell the customer there was a technical problem and CALL create_promise once more with the same product, amount and date.'
        else:
            failed = _load('service_error_products', [])
            failed.append(attempt.get('product_id'))
            vars['service_error_products'] = json.dumps(failed)
            d['what_to_do_next'] = 'NOT recorded after two attempts. Tell the customer you could not record this promise today. Never say it is recorded. ' + str(__SERVICE_ERROR_NEXT__)
except Exception:
    pass
"""

NOTE_PRE = """import json
try:
    b = config.get('body') if isinstance(config, dict) else None
    if isinstance(b, dict):
        vars['note_attempt'] = json.dumps({'product_id': b.get('product_id'), 'reason': b.get('reason')})
except Exception:
    pass
"""

NOTE_POST = """import json
__COMMON__
try:
    d = _d(result)
    if d is not None and _flag(d.get('ok')):
        notes = _load('notes_recorded', [])
        notes.append(_load('note_attempt', {}))
        vars['notes_recorded'] = json.dumps(notes)
        d['what_to_do_next'] = 'Note recorded. Continue with the next product, or if every product is handled, thank the customer, say goodbye and call transition_to_wrap_up.'
    elif d is not None:
        d['what_to_do_next'] = 'The note was not recorded. CALL add_note once more with the same values.'
except Exception:
    pass
"""

TRANSFER_PRE = """try:
    b = config.get('body') if isinstance(config, dict) else None
    if isinstance(b, dict):
        vars['transfer_queue'] = str(b.get('queue') or '')
except Exception:
    pass
"""

TRANSFER_POST = """import json
__COMMON__
try:
    d = _d(result)
    if d is not None and _flag(d.get('ok')):
        vars['transfer_state'] = 'done'
        d['what_to_do_next'] = 'Transfer requested. Tell the customer you are connecting them now, thank them and say goodbye. Do not record any note after this.'
    elif d is not None:
        d['what_to_do_next'] = 'The transfer failed. Apologise, say a colleague will call back, thank the customer and say goodbye.'
except Exception:
    pass
"""

CALLBACK_POST = """import json
__COMMON__
try:
    d = _d(result)
    if d is not None and _flag(d.get('ok')):
        vars['callback_state'] = 'done'
        d['what_to_do_next'] = 'Callback booked. Thank the person and say goodbye.'
    elif d is not None:
        d['what_to_do_next'] = 'The callback could not be booked. CALL schedule_callback once more with the same date and time.'
except Exception:
    pass
"""

CLOSE_PRE = """try:
    b = config.get('body') if isinstance(config, dict) else None
    NO_REASON = __NO_REASON__
    if isinstance(b, dict):
        if not b.get('outcome'):
            b['outcome'] = str(vars.get('outcome') or __DEFAULT_OUTCOME__)
        if not b.get('reason'):
            b['reason'] = str(vars.get('reason') or '')
        if b.get('outcome') in NO_REASON or not b.get('reason'):
            b.pop('reason', None)
except Exception:
    pass
"""


def all_hooks(policy):
    """Every hook's source, keyed by tool name and phase, filled from the policy."""
    ident, out = policy.get("identity", {}), policy.get("outcomes", {})
    default_outcome = (out.get("unclear") or {}).get("outcome", "")
    multi = policy.get("multi_product", {}).get("enabled")
    service_next = ("CALL add_note for this product with reason " + json.dumps(policy.get("note_reasons", {}).get("service_error", "service_error")) + ", then continue.") if multi else "Then thank the customer and say goodbye."
    return {
        ("verify_identity", "post"): fill(VERIFY_POST, common=COMMON, identity=ident),
        ("create_promise", "pre"): fill(PROMISE_PRE, common=COMMON, cal=policy.get("calendar", {})),
        ("create_promise", "post"): fill(PROMISE_POST, common=COMMON, after_promise=json.dumps(policy.get("sentences", {}).get("after_promise", "")), service_error_next=json.dumps(service_next)),
        ("add_note", "pre"): NOTE_PRE, ("add_note", "post"): fill(NOTE_POST, common=COMMON),
        ("transfer_to_agent", "pre"): TRANSFER_PRE, ("transfer_to_agent", "post"): fill(TRANSFER_POST, common=COMMON),
        ("schedule_callback", "post"): fill(CALLBACK_POST, common=COMMON),
        ("close_call", "pre"): fill(CLOSE_PRE, no_reason=policy.get("no_reason_outcomes", []), default_outcome=json.dumps(default_outcome)),
    }
