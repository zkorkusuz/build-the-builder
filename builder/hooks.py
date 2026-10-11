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
def _block(b):
    # the platform sends the request even with an empty body and skips the post-hook on an error, so a blocked call sends values no bank accepts
    for k in list(b):
        if k != 'customer_id':
            b[k] = 'blocked'
"""

VERIFY_PRE = """__DATES_SRC__
import json
__COMMON__
P = __IDENTITY__
try:
    b = config.get('body') if isinstance(config, dict) else None
    vars['id_block'] = ''
    if isinstance(b, dict):
        field, answer = str(b.get('field') or ''), str(b.get('answer') or '').strip()
        vars['id_current_field'] = field
        q = next((x for x in (P.get('questions') or []) if str(x.get('field')) == field), dict())
        fmt = str(q.get('format') or '').lower()
        prev = str(vars.get('id_partial_' + field) or '')
        WORDS = {'zero': 0, 'oh': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10}
        # a date said in parts is kept until a full one arrives, and a repeat or a fuller answer replaces it
        combined = answer if (not prev or prev in answer) else (prev if answer in prev else prev + ' ' + answer)
        datelike = 'yyyy' in fmt or 'date' in fmt or 'date' in field or 'birth' in field and 'year' not in field
        digits_needed = 0
        m = re.search(r'(\\d+|one|two|three|four|five|six|seven|eight|nine|ten)\\s*digit', fmt)
        if m:
            digits_needed = WORDS.get(m.group(1), 0) or int(m.group(1))
        if datelike:
            d = parse_full_date(combined, str(P.get('numeric_date_order') or 'day_month_year'))
            if d is not None:
                b['answer'] = d.isoformat()
                vars['id_partial_' + field] = ''
            else:
                vars['id_partial_' + field] = combined
                vars['id_block'] = 'INCOMPLETE answer for ' + field + ': so far ' + json.dumps(combined) + ', which is not a full date. Ask the customer only for the missing part (day, month or year) and CALL verify_identity again with just that part; the parts are combined for you. This is not a wrong answer.'
                _block(b)
        elif digits_needed:
            # number words become digits; a value that extends the digits held so far is the model's own join, anything else is the next part
            spoken = re.sub(r'[a-z]+', lambda w: str(WORDS[w.group(0)]) if w.group(0) in WORDS else w.group(0), answer.lower())
            new = re.sub(r'\\D', '', spoken)
            digits = new if (prev and new.startswith(prev) and len(new) > len(prev)) else prev + new
            if len(digits) >= digits_needed:
                b['answer'] = digits[-digits_needed:]
                vars['id_partial_' + field] = ''
            else:
                vars['id_partial_' + field] = digits
                vars['id_block'] = 'INCOMPLETE answer for ' + field + ': ' + str(len(digits)) + ' of ' + str(digits_needed) + ' digits so far. Ask the customer for the rest and CALL verify_identity again with whatever digits they say next, even a single one; the parts are combined for you. This is not a wrong answer.'
                _block(b)
except Exception:
    pass
"""

VERIFY_POST = """import json
__COMMON__
try:
    d = _d(result)
    P = __IDENTITY__
    block = str(vars.get('id_block') or '')
    if d is None and isinstance(result, dict):
        result['data'] = d = dict()
    if block:
        vars['id_block'] = ''
        if d is not None:
            d['what_to_do_next'] = block
    elif d is not None:
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
            field = str(vars.get('id_current_field') or 'the same field')
            rule = str(P.get('on_wrong') or 'Follow your instructions for a wrong answer, then CALL verify_identity again.')
            d['what_to_do_next'] = 'WRONG ANSWER for ' + field + '. ' + str(left) + ' wrong answers left in total. ' + rule + ' (The field just checked was ' + field + '.)'
except Exception:
    pass
"""

PROMISE_PRE = """__DATES_SRC__
import json
__COMMON__
CAL = __CAL__
ADJ = __ADJ__
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
            _block(b)
        elif f.get('floor') is not None and float(b.get('amount') or 0) < float(f.get('floor')) - 0.005:
            vars['promise_block'] = 'NOT recorded: the amount ' + str(b.get('amount')) + ' is below the floor of ' + str(f.get('floor')) + ' for this product. Tell the customer it cannot be recorded and offer the floor amount once, as your instructions say.'
            _block(b)
        else:
            today = datetime.date.fromisoformat(str(vars.get('today'))[:10])
            try:
                day = datetime.date.fromisoformat(str(b.get('date'))[:10])
            except ValueError:
                day = parse_day_words(b.get('date'), today)
            deadline = datetime.date.fromisoformat(str(f.get('deadline'))[:10])
            if day is None:
                vars['promise_block'] = 'NOT recorded: the date ' + str(b.get('date')) + ' could not be read. CALL create_promise again with the date as YYYY-MM-DD or in the customer\\'s own words (for example next Friday, Monday the 19th, 20 November).'
                _block(b)
            else:
                use, why = adjust_day(day, today, deadline, CAL, ADJ)
                if why:
                    vars['promise_block'] = 'NOT recorded: the date ' + day.isoformat() + ' ' + why + '. Read the promise back again with the new date and CALL create_promise only after the customer confirms it.'
                    _block(b)
                else:
                    b['date'] = day.isoformat()
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
        vars['offer_now'] = ''
        done.append(attempt)
        vars['promises_recorded'] = json.dumps(done)
        vars['promise_failures'] = '0'
        vars['promise_state'] = 'recorded'
        text = 'Recorded: ' + str(attempt.get('words') or 'the product') + ', ' + str(attempt.get('amount')) + ' on ' + str(attempt.get('date')) + '.'
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
        d['what_to_do_next'] = 'Transfer requested. Tell the customer you are connecting them now, thank them and say goodbye.'
    elif d is not None:
        d['what_to_do_next'] = 'The transfer failed. CALL transfer_to_agent once more with the same queue.' if _count('transfer_failures') < 2 else 'The transfer could not be made now. Tell the customer so, thank them and say goodbye. Do not promise any call back.'
except Exception:
    pass
"""

CALLBACK_PRE = """import json, datetime, re
__COMMON__
CB = __CALLBACK__
WORDS = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11, 'twelve': 12, 'noon': 12, 'midday': 12, 'midnight': 0}
DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
def _day(text, today):
    t = str(text or '').strip().lower()
    m = re.search(r'(\\d{4})-(\\d{2})-(\\d{2})', t)
    if m:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    if 'today' in t or 'tonight' in t or 'this evening' in t or 'this afternoon' in t or 'this morning' in t or t in ('now', 'later'):
        return today
    if 'day after tomorrow' in t:
        return today + datetime.timedelta(days=2)
    if 'tomorrow' in t:
        return today + datetime.timedelta(days=1)
    for i, name in enumerate(DAYS):
        if name in t or name[:3] in t.split():
            ahead = (i - today.weekday()) % 7
            if 'next' in t:
                ahead = ahead + 7 if ahead else 7
            return today + datetime.timedelta(days=ahead)
    m = re.search(r'(\\d{1,2})(?:st|nd|rd|th)?\\s*(?:of\\s*)?([a-z]+)?', t)
    if m and m.group(1):
        d = int(m.group(1))
        months = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']
        mon = next((k + 1 for k, n in enumerate(months) if m.group(2) and n.startswith(m.group(2)[:3])), today.month)
        try:
            cand = datetime.date(today.year, mon, d)
            return cand if cand >= today else datetime.date(today.year + 1, mon, d)
        except ValueError:
            pass
    return None
def _time(text):
    t = str(text or '').strip().lower().replace('.', ':')
    extra = 0
    if 'half past' in t:
        t, extra = t.replace('half past', ''), 30
    elif 'quarter past' in t:
        t, extra = t.replace('quarter past', ''), 15
    elif 'quarter to' in t:
        t, extra = t.replace('quarter to', ''), -15
    m = re.search(r'(\\d{1,2})(?::(\\d{2}))?\\s*(am|pm|a\\.m|p\\.m)?', t)
    h, mi = None, 0
    if m:
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        if m.group(3) and m.group(3).startswith('p') and h < 12:
            h += 12
        if m.group(3) and m.group(3).startswith('a') and h == 12:
            h = 0
    else:
        for w, n in WORDS.items():
            if re.search(r'\\b' + w + r'\\b', t):
                h = n
                break
    if h is None:
        return None
    if not m or not m.group(3):
        if ('evening' in t or 'tonight' in t or 'afternoon' in t or 'pm' in t) and h < 12:
            h += 12
        elif 1 <= h <= 6 and 'morning' not in t and 'am' not in t.split():
            h += 12
    mi += extra
    if mi < 0:
        h, mi = h - 1, mi + 60
    if h > 23 or h < 0:
        return None
    return '%02d:%02d' % (h, mi)
try:
    b = config.get('body') if isinstance(config, dict) else None
    vars['callback_block'] = ''
    if isinstance(b, dict) and (CB.get('days') or CB.get('from') or CB.get('to')):
        today = datetime.date.fromisoformat(str(vars.get('today'))[:10])
        nb = datetime.date.fromisoformat(str(vars.get('callback_next_business_day') or vars.get('next_business_day'))[:10])
        day, t = _day(b.get('date'), today), _time(str(b.get('time') or '') + ' ' + str(b.get('date') or ''))
        now_t, days = str(vars.get('now_time') or ''), CB.get('days') or []
        frm, to = str(CB.get('from') or ''), str(CB.get('to') or '')
        if day is None or t is None:
            vars['callback_block'] = 'NOT booked: the day or the time could not be read. CALL schedule_callback again with date as the day the person said (today, tomorrow, a weekday name, or YYYY-MM-DD) and time as they said it (for example 9pm or 10:30); today is ' + today.isoformat() + ' and the next business day is ' + nb.isoformat() + '. Do not ask the person for a date.'
            _block(b)
        else:
            b['date'], b['time'] = day.isoformat(), t
            ok_day = (day == today and 'today' in days) or (day == nb and 'next_business_day' in days)
            ok_time = (not frm or t >= frm) and (not to or t <= to) and not (day == today and now_t and t <= now_t)
            if not (ok_day and ok_time):
                n = _count('callback_outside')
                limit = int(float(CB.get('max_asks') or 1))
                if n <= limit:
                    vars['callback_block'] = 'NOT booked: ' + day.isoformat() + ' at ' + t + ' is outside the callback window (' + str(vars.get('callback_text') or '') + '). Ask for another day and time inside it, then CALL schedule_callback again.'
                else:
                    vars['callback_block'] = 'NOT booked: that is outside the window again. Do not book anything and do not ask again. Thank the person, say goodbye, and in the same message call transition_to_outcome_no_callback_quiet.'
                _block(b)
except Exception:
    pass
"""

CALLBACK_POST = """import json
__COMMON__
try:
    d = _d(result)
    block = str(vars.get('callback_block') or '')
    if d is None and isinstance(result, dict):
        result['data'] = d = dict()
    if block:
        vars['callback_block'] = ''
        if d is not None:
            d['what_to_do_next'] = block
    elif d is not None and _flag(d.get('ok')):
        vars['callback_state'] = 'done'
        d['what_to_do_next'] = 'Callback booked. Thank the person and say goodbye.'
    elif d is not None:
        d['what_to_do_next'] = 'The callback could not be booked. CALL schedule_callback once more with the same date and time.' if _count('callback_failures') < 2 else 'The callback could not be booked now. Tell the person so, thank them and say goodbye.'
except Exception:
    pass
"""

CLOSE_PRE = """__RECOMPUTE__
try:
    b = config.get('body') if isinstance(config, dict) else None
    NO_REASON = __NO_REASON__
    if isinstance(b, dict):
        o, r = str(vars.get('outcome') or ''), str(vars.get('reason') or '')
        if o:
            b['outcome'] = o
        elif not b.get('outcome') or '{' in str(b.get('outcome')):
            b['outcome'] = __DEFAULT_OUTCOME__
        if r:
            b['reason'] = r
        if b.get('outcome') in NO_REASON or not b.get('reason') or '{' in str(b.get('reason')):
            b.pop('reason', None)
except Exception:
    pass
"""


def all_hooks(policy, recompute="", dates_src=""):
    """Every hook's source, keyed by tool name and phase, filled from the policy."""
    ident, out = policy.get("identity") or {}, policy.get("outcomes") or {}
    default_outcome = (out.get("unclear") or {}).get("outcome", "")
    multi = (policy.get("multi_product") or {}).get("enabled")
    note_value = next((e.get("note_reason") for e in policy.get("end_reasons") or [] if e.get("key") == "service_error" and e.get("note_reason")), "")
    service_next = ("CALL add_note for this product with reason " + json.dumps(note_value) + ", then continue.") if (multi and note_value) else "Then continue with the other products, or thank the customer and say goodbye."
    return {
        ("verify_identity", "pre"): fill(VERIFY_PRE, dates_src=dates_src, common=COMMON, identity=ident), ("verify_identity", "post"): fill(VERIFY_POST, common=COMMON, identity=ident),
        ("create_promise", "pre"): fill(PROMISE_PRE, dates_src=dates_src, common=COMMON, cal=policy.get("calendar") or {}, adj=policy.get("date_adjust") or {}),
        ("create_promise", "post"): fill(PROMISE_POST, common=COMMON, after_promise=json.dumps((policy.get("sentences") or {}).get("after_promise", "")), service_error_next=json.dumps(service_next)),
        ("add_note", "pre"): NOTE_PRE, ("add_note", "post"): fill(NOTE_POST, common=COMMON),
        ("transfer_to_agent", "pre"): TRANSFER_PRE, ("transfer_to_agent", "post"): fill(TRANSFER_POST, common=COMMON),
        ("schedule_callback", "pre"): fill(CALLBACK_PRE, common=COMMON, callback=policy.get("callback") or {}), ("schedule_callback", "post"): fill(CALLBACK_POST, common=COMMON),
        ("close_call", "pre"): fill(CLOSE_PRE, recompute=recompute or "", no_reason=policy.get("no_reason_outcomes") or [], default_outcome=json.dumps(default_outcome)),
    }
