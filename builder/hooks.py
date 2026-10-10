"""Python hooks that run on Freya around each tool call, as source strings filled from the policy.

Every hook is wrapped in try/except, reads and writes through `vars`, holds no bank's values of its own, and never
contains two braces in a row: policy values are inserted as indented JSON with `__NAME__` placeholders.
"""
import json


def literal(value):
    """A JSON literal safe for a Freya code string: indented so that no two braces touch."""
    return json.dumps(value, indent=1).replace("}}", "} }").replace("{{", "{ {")


def fill(template, **values):
    for name, value in values.items():
        template = template.replace("__" + name.upper() + "__", value if isinstance(value, str) else literal(value))
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
def _count(name):
    n = int(float(vars.get(name) or 0)) + 1
    vars[name] = str(n)
    return n
"""

VERIFY_POST = """import json
__COMMON__
try:
    d = _d(result)
    P = __IDENTITY__
    if d is not None:
        left = d.get('wrong_answers_left')
        hint = str(d.get('hint') or '')
        if _flag(d.get('all_verified')):
            vars['id_state'] = 'verified'
            d['what_to_do_next'] = 'All security questions passed. The identity check is complete.'
        elif hint and P.get('hint_value') and hint == str(P.get('hint_value')):
            d['what_to_do_next'] = str(P.get('hint_instruction') or 'The service returned the hint ' + hint + '. Follow your instructions for it and CALL verify_identity again with the same field.')
        elif not _flag(d.get('ok')):
            d['what_to_do_next'] = 'The answer could not be read in the required format (' + str(d.get('error') or '') + '). Ask the customer to repeat it, then CALL verify_identity again with the same field. This is not counted as a wrong answer.'
        elif _flag(d.get('verified')):
            d['what_to_do_next'] = 'Correct. Now ask the next security question in the order of your instructions and CALL verify_identity with its answer. If there is no next question, wait: the check is complete.'
        elif left is not None and int(float(left)) <= 0:
            vars['id_state'] = 'failed'
            d['what_to_do_next'] = 'The identity check has failed. Do not mention any account or debt. ' + ('Tell the customer: ' + str(P.get('on_fail_sentence')) + ' ' if P.get('on_fail_sentence') else '') + 'Then thank them and say goodbye.'
        else:
            d['what_to_do_next'] = 'Wrong answer. ' + str(left) + ' wrong answers left in total. Ask the same question once more and CALL verify_identity again with the new answer.'
except Exception:
    pass
"""

PROMISE_PRE = """import json, datetime
__COMMON__
CAL = __CAL__
def _biz(day):
    return day.weekday() in (CAL.get('business_weekdays') or [0, 1, 2, 3, 4]) and day.isoformat() not in (CAL.get('holidays') or [])
try:
    b = config.get('body') if isinstance(config, dict) else None
    facts = _load('product_facts_json', [])
    vars['promise_block'] = ''
    if isinstance(b, dict) and facts:
        ids = [f.get('product_id') for f in facts]
        if b.get('product_id') not in ids and len(facts) == 1:
            b['product_id'] = ids[0]
        f = next((x for x in facts if x.get('product_id') == b.get('product_id')), None)
        vars['promise_attempt'] = json.dumps({'product_id': b.get('product_id'), 'amount': b.get('amount'), 'date': b.get('date'), 'words': (f or {}).get('words', '')})
        if f is None:
            vars['promise_block'] = 'NOT recorded: product_id ' + str(b.get('product_id')) + ' is not one of the customer products. Use exactly one of these ids: ' + ', '.join(str(x) for x in ids) + ' and CALL create_promise again.'
            config['body'] = dict()
        elif f.get('floor') is not None and float(b.get('amount') or 0) < float(f.get('floor')) - 0.005:
            vars['promise_block'] = 'NOT recorded: the amount ' + str(b.get('amount')) + ' is below the floor of ' + str(f.get('floor')) + ' for this product. Tell the customer it cannot be recorded and offer the floor amount once, as your instructions say.'
            config['body'] = dict()
        else:
            today = datetime.date.fromisoformat(str(vars.get('today'))[:10])
            day = datetime.date.fromisoformat(str(b.get('date'))[:10])
            deadline = datetime.date.fromisoformat(str(f.get('deadline'))[:10])
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
    block = str(vars.get('promise_block') or '')
    if d is None and isinstance(result, dict):
        result['data'] = d = dict()
    if block:
        vars['promise_block'] = ''
        if d is not None:
            d['what_to_do_next'] = block
    elif d is not None and _flag(d.get('ok')):
        done.append(attempt)
        vars['promises_recorded'] = json.dumps(done)
        vars['promise_failures'] = '0'
        vars['promise_state'] = 'recorded'
        note = str(vars.get('promise_date_note') or '')
        text = 'Recorded: ' + str(attempt.get('words') or 'the product') + ', ' + str(attempt.get('amount')) + ' on ' + str(attempt.get('date')) + '.'
        if note:
            text += ' The date was ' + note + '; tell the customer the recorded date.'
        text += ' Tell the customer the promise is recorded' + (' and then say exactly: ' + json.dumps(sentence) if sentence else '') + '.'
        text += ' Then continue with any product that still has no promise, or thank the customer, say goodbye and call transition_to_wrap_up.'
        d['what_to_do_next'] = text
    elif d is not None and isinstance(d.get('error'), str) and d.get('error') and int(float(result.get('status_code') or 200)) < 500:
        d['what_to_do_next'] = 'NOT recorded: the bank rejected the call (' + d.get('error') + '). Correct the values and CALL create_promise again. product_id must be exactly the id shown in your facts.'
    else:
        n = _count('promise_failures')
        vars['promise_state'] = 'failed'
        if d is not None and n < 2:
            d['what_to_do_next'] = 'NOT recorded: the service failed. Tell the customer there was a technical problem and CALL create_promise once more with the same product, amount and date.'
        elif d is not None:
            failed = _load('service_error_products', [])
            failed.append(attempt.get('product_id'))
            vars['service_error_products'] = json.dumps(failed)
            d['what_to_do_next'] = 'NOT recorded after two attempts. Tell the customer you could not record this promise today. Never say it is recorded. ' + __SERVICE_ERROR_NEXT__
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
        d['what_to_do_next'] = 'The note was not recorded. CALL add_note once more with the same values.' if _count('note_failures') < 2 else 'The note could not be recorded. Continue without it.'
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
        d['what_to_do_next'] = 'The transfer failed. CALL transfer_to_agent once more with the same queue.' if _count('transfer_failures') < 2 else 'The transfer could not be made now. Tell the customer so, thank them and say goodbye. Do not promise any call back.'
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
        d['what_to_do_next'] = 'The callback could not be booked. CALL schedule_callback once more with the same date and time.' if _count('callback_failures') < 2 else 'The callback could not be booked now. Tell the person so, thank them and say goodbye.'
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
    ident, out = policy.get("identity") or {}, policy.get("outcomes") or {}
    default_outcome = (out.get("unclear") or {}).get("outcome", "")
    multi = (policy.get("multi_product") or {}).get("enabled")
    note_value = next((e.get("note_reason") for e in policy.get("end_reasons") or [] if e.get("key") == "service_error" and e.get("note_reason")), "")
    service_next = ("CALL add_note for this product with reason " + json.dumps(note_value) + ", then continue.") if (multi and note_value) else "Then continue with the other products, or thank the customer and say goodbye."
    return {
        ("verify_identity", "post"): fill(VERIFY_POST, common=COMMON, identity=ident),
        ("create_promise", "pre"): fill(PROMISE_PRE, common=COMMON, cal=policy.get("calendar") or {}),
        ("create_promise", "post"): fill(PROMISE_POST, common=COMMON, after_promise=json.dumps((policy.get("sentences") or {}).get("after_promise", "")), service_error_next=json.dumps(service_next)),
        ("add_note", "pre"): NOTE_PRE, ("add_note", "post"): fill(NOTE_POST, common=COMMON),
        ("transfer_to_agent", "pre"): TRANSFER_PRE, ("transfer_to_agent", "post"): fill(TRANSFER_POST, common=COMMON),
        ("schedule_callback", "post"): fill(CALLBACK_POST, common=COMMON),
        ("close_call", "pre"): fill(CLOSE_PRE, no_reason=policy.get("no_reason_outcomes") or [], default_outcome=json.dumps(default_outcome)),
    }
