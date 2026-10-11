"""Python hooks that run on Freya around each tool call, as source strings filled from the policy.

Every hook is wrapped in try/except, reads and writes through `vars`, holds no bank's values of its own, and never
contains two braces in a row: policy values are inserted as indented JSON with `__NAME__` placeholders.
"""
import json
from builder.fields import default_fields


def literal(value):
    """A JSON literal safe for a Freya code string: indented so that no two braces touch, with no null or boolean, which Python cannot read."""
    return json.dumps(plain(value), indent=1).replace("}}", "} }").replace("{{", "{ {")


def plain(value):
    """The value with every null as an empty string and every boolean as its word, so that it reads as Python."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v) for v in value]
    return value


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
def _ok(d, F):
    # an empty answer is a failed or lost call; a service without a success flag names a failure in an error field
    if not d:
        return False
    if F.get('ok') in d:
        return _flag(d.get(F['ok']))
    return not any(v is not None and str(v).strip().lower() not in ('', 'false', '0', '[]', '{}') for k, v in d.items() if str(k).lower().startswith('error'))
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
F = __FIELDS__
try:
    b = config.get('body') if isinstance(config, dict) else None
    vars['id_block'] = ''
    if isinstance(b, dict):
        field, answer = str(b.get(F['field']) or ''), str(b.get(F['answer']) or '').strip()
        vars['id_current_field'] = field
        q = next((x for x in (P.get('questions') or []) if str(x.get('field')) == field), dict())
        fmt = str(q.get('format') or '').lower()
        prev = str(vars.get('id_partial_' + field) or '')
        WORDS = {'zero': 0, 'oh': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10}
        datelike = 'yyyy' in fmt or 'date' in fmt or 'date' in field or 'birth' in field and 'year' not in field
        digits_needed = 0
        m = re.search(r'(\\d+|one|two|three|four|five|six|seven|eight|nine|ten)\\s*digit', fmt)
        if m:
            digits_needed = WORDS.get(m.group(1), 0) or int(m.group(1))
        if datelike:
            held = _load('id_partial_' + field, dict())
            new = date_parts(answer, str(P.get('numeric_date_order') or 'day_month_year'))
            # parts the customer already gave are kept and a later answer fills only what is missing, because the model's own join of the parts is sometimes wrong; the cost is that a correction of an earlier part is dropped until the bank marks the answer wrong
            parts = dict((k, (held.get(k) if isinstance(held, dict) else None) or new.get(k)) for k in ('day', 'month', 'year'))
            missing = [k for k in parts if parts[k] is None]
            d = None
            if not missing:
                try:
                    d = datetime.date(parts['year'], parts['month'], parts['day'])
                except ValueError:
                    parts, missing = dict(day=None, month=None, year=None), ['whole date, because the parts given do not make a real date']
            if d is not None:
                b[F['answer']] = d.isoformat()
                vars['id_partial_' + field] = ''
            else:
                vars['id_partial_' + field] = json.dumps(parts)
                vars['id_block'] = 'INCOMPLETE answer for ' + field + ': missing the ' + ' and '.join(missing) + '. Ask the customer only for that and CALL verify_identity again with what they say; the parts are combined for you. This is not a wrong answer.'
                _block(b)
        elif digits_needed:
            # number words become digits; a value that extends the digits held so far is the model's own join, anything else is the next part
            spoken = re.sub(r'[a-z]+', lambda w: str(WORDS[w.group(0)]) if w.group(0) in WORDS else w.group(0), answer.lower())
            new = re.sub(r'\\D', '', spoken)
            digits = new if (prev and new.startswith(prev) and len(new) > len(prev)) else prev + new
            if len(digits) >= digits_needed:
                b[F['answer']] = digits[-digits_needed:]
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
F = __FIELDS__
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
        left = d.get(F['wrong_answers_left'])
        hint = str(d.get(F['hint']) or '')
        if _flag(d.get(F['all_verified'])):
            vars['id_state'] = 'verified'
            d['what_to_do_next'] = 'All security questions passed. The identity check is complete.'
        elif hint.lower() not in ('', 'false', '0'):
            # a hint is never a wrong answer, whether or not the policy named it
            d['what_to_do_next'] = str(P.get('hint_instruction') if hint == str(P.get('hint_value')) and P.get('hint_instruction') else 'The service returned the hint ' + hint + '. Follow your instructions for it and CALL verify_identity again with the same field. This is not counted as a wrong answer.')
        elif not _ok(d, F):
            d['what_to_do_next'] = 'The answer could not be read in the required format (' + str(d.get(F['error']) or '') + '). Ask the customer to repeat it, then CALL verify_identity again with the same field. This is not counted as a wrong answer.'
        elif _flag(d.get(F['verified'])):
            # a service without an all-verified flag: the check is complete once every question's field has passed
            done = _load('id_verified_fields', [])
            field = str(vars.get('id_current_field') or '')
            if field and field not in done:
                done.append(field)
            vars['id_verified_fields'] = json.dumps(done)
            needed = [str(q.get('field')) for q in (P.get('questions') or [])]
            if needed and (all(f in done for f in needed) or len(done) >= len(needed)):
                vars['id_state'] = 'verified'
                d['what_to_do_next'] = 'All security questions passed. The identity check is complete.'
            else:
                d['what_to_do_next'] = 'Correct. Now ask the next security question in the order of your instructions and CALL verify_identity with its answer. If there is no next question, wait: the check is complete.'
        else:
            n = _count('id_wrong_total')          # the hook's own count, for a service that does not say how many wrong answers are left
            try:
                left = int(float(left))
            except (TypeError, ValueError):
                try:
                    maxw = int(float(P.get('max_wrong_total') or 0))
                except (TypeError, ValueError):
                    maxw = 0
                left = maxw - n if maxw else None
            if left is not None and left <= 0:
                vars['id_state'] = 'failed'
                d['what_to_do_next'] = 'The identity check has failed. Do not mention any account or debt. ' + ('Tell the customer: ' + str(P.get('on_fail_sentence')) + ' ' if P.get('on_fail_sentence') else '') + 'Then thank them and say goodbye.'
            else:
                field = str(vars.get('id_current_field') or 'the same field')
                rule = str(P.get('on_wrong') or 'Follow your instructions for a wrong answer, then CALL verify_identity again.')
                d['what_to_do_next'] = 'WRONG ANSWER for ' + field + '. ' + (str(left) + ' wrong answers left in total. ' if left is not None else '') + rule + ' (The field just checked was ' + field + '.)'
except Exception:
    pass
"""

PROMISE_PRE = """__DATES_SRC__
import json
__COMMON__
CAL = __CAL__
ADJ = __ADJ__
F = __FIELDS__
try:
    b = config.get('body') if isinstance(config, dict) else None
    facts = _load('product_facts_json', [])
    done = _load('promises_recorded', [])
    vars['promise_block'] = ''
    failed_turn, turn = str(vars.get('promise_failed_turn') or ''), str(vars.get('negotiate.current_turns') or '')
    if failed_turn and failed_turn != turn:
        vars['promise_failed_turn'] = ''
    if isinstance(b, dict) and facts and failed_turn and failed_turn == turn:
        # the model retries a failed recording in the same breath; the customer must hear about the problem first
        vars['promise_block'] = 'NOT yet: first tell the customer there was a technical problem recording it, and that you will try once more. CALL create_promise again with the same values after they reply.'
        _block(b)
    elif isinstance(b, dict) and facts:
        ids = [f.get('product_id') for f in facts]
        if b.get(F['product_id']) not in ids and len(facts) == 1:
            b[F['product_id']] = ids[0]
        f = next((x for x in facts if x.get('product_id') == b.get(F['product_id'])), None)
        x = next((x for x in done if str(x.get('product_id')) == str(b.get(F['product_id']))), None)
        if f is None:
            vars['promise_block'] = 'NOT recorded: ' + F['product_id'] + ' ' + str(b.get(F['product_id'])) + ' is not one of the customer products. Use exactly one of these ids: ' + ', '.join(str(x) for x in ids) + ' and CALL create_promise again.'
            _block(b)
        elif x is not None:
            # the bank takes one promise per product, so a retry after a lost answer or a change of mind must not reach it
            vars['promise_block'] = 'ALREADY recorded earlier in this call: ' + str(f.get('words') or 'this product') + ', ' + str(x.get('amount')) + ' on ' + str(x.get('date')) + '. The bank takes one promise per product, so do not CALL create_promise for it again; if the customer wants it changed, follow your instructions. Then continue with any product that still has no promise, or thank the customer, say goodbye and call transition_to_wrap_up.'
            _block(b)
        elif f.get('floor') is not None and float(b.get(F['amount']) or 0) < float(f.get('floor')) - 0.005:
            vars['promise_block'] = 'NOT recorded: the amount ' + str(b.get(F['amount'])) + ' is below the floor of ' + str(f.get('floor')) + ' for this product. Tell the customer it cannot be recorded and offer the floor amount once, as your instructions say.'
            _block(b)
        else:
            today = datetime.date.fromisoformat(str(vars.get('today'))[:10])
            try:
                day = datetime.date.fromisoformat(str(b.get(F['date']))[:10])
            except ValueError:
                day = parse_day_words(b.get(F['date']), today)
            deadline = datetime.date.fromisoformat(str(f.get('deadline'))[:10])
            if day is None:
                vars['promise_block'] = 'NOT recorded: the date ' + str(b.get(F['date'])) + ' could not be read. CALL create_promise again with the date as YYYY-MM-DD or in the customer\\'s own words (for example next Friday, Monday the 19th, 20 November).'
                _block(b)
            else:
                use, why = adjust_day(day, today, deadline, CAL, ADJ)
                if why:
                    vars['promise_block'] = 'NOT recorded: the date ' + day.isoformat() + ' ' + why + '. Read the promise back again with the new date and CALL create_promise only after the customer confirms it.'
                    _block(b)
                else:
                    b[F['date']] = day.isoformat()
                    # the attempt is kept with the date the bank receives, so the post-hook reads back and compares the same value
                    vars['promise_attempt'] = json.dumps({'product_id': b.get(F['product_id']), 'amount': b.get(F['amount']), 'date': b[F['date']], 'words': f.get('words', '')})
except Exception:
    pass
"""

PROMISE_POST = """import json
__COMMON__
F = __FIELDS__
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
    elif d is not None and _ok(d, F):
        vars['offer_now'] = ''
        done.append(attempt)
        vars['promises_recorded'] = json.dumps(done)
        vars['promise_failures'] = '0'
        vars['promise_state'] = 'recorded'
        text = 'Recorded: ' + str(attempt.get('words') or 'the product') + ', ' + str(attempt.get('amount')) + ' on ' + str(attempt.get('date')) + '.'
        text += ' Tell the customer the promise is recorded' + (' and then say exactly: ' + json.dumps(sentence) if sentence else '') + '.'
        text += ' Then continue with any product that still has no promise, or thank the customer, say goodbye and call transition_to_wrap_up.'
        d['what_to_do_next'] = text
    elif d is not None and isinstance(d.get(F['error']), str) and d.get(F['error']) and int(float(result.get('status_code') or 200)) < 500:
        if 'already' in str(d.get(F['error'])).lower() and attempt:
            # the bank holds a promise this call never saw confirmed (a lost answer): it is recorded, and saying otherwise would be the honesty failure
            done.append(attempt); vars['promises_recorded'] = json.dumps(done); vars['promise_state'] = 'recorded'; vars['offer_now'] = ''
            d['what_to_do_next'] = 'The bank already holds this promise: ' + str(attempt.get('words') or 'the product') + ', ' + str(attempt.get('amount')) + ' on ' + str(attempt.get('date')) + '. Tell the customer it is recorded, then continue with any product that still has no promise, or thank the customer, say goodbye and call transition_to_wrap_up.'
        elif _count('promise_failures') < 3:
            d['what_to_do_next'] = 'NOT recorded: the bank rejected the call (' + str(d.get(F['error'])) + '). Correct the values and CALL create_promise again. ' + F['product_id'] + ' must be exactly the id shown in your facts.'
        else:
            d['what_to_do_next'] = 'NOT recorded: the bank rejected the call three times (' + str(d.get(F['error'])) + '). Never say it is recorded. Tell the customer you could not record it today, then thank them, say goodbye and call transition_to_wrap_up.'
    else:
        n = _count('promise_failures')
        vars['promise_state'] = 'failed'
        if d is not None and n < 2:
            vars['promise_failed_turn'] = str(vars.get('negotiate.current_turns') or '')
            d['what_to_do_next'] = 'NOT recorded: the service failed. Tell the customer there was a technical problem and that you will try once more; after they reply, CALL create_promise once more with the same product, amount and date.'
        elif d is not None:
            failed = _load('service_error_products', [])
            failed.append(attempt.get('product_id'))
            vars['service_error_products'] = json.dumps(failed)
            d['what_to_do_next'] = 'NOT recorded after two attempts. Tell the customer you could not record this promise today. Never say it is recorded. ' + __SERVICE_ERROR_NEXT__
except Exception:
    pass
"""

NOTE_PRE = """import json
F = __FIELDS__
try:
    b = config.get('body') if isinstance(config, dict) else None
    if isinstance(b, dict):
        vars['note_attempt'] = json.dumps({'product_id': b.get(F['product_id']), 'reason': b.get(F['reason'])})
except Exception:
    pass
"""

NOTE_POST = """import json
__COMMON__
F = __FIELDS__
try:
    d = _d(result)
    if d is not None and _ok(d, F):
        notes = _load('notes_recorded', [])
        notes.append(_load('note_attempt', {}))
        vars['notes_recorded'] = json.dumps(notes)
        d['what_to_do_next'] = 'Note recorded. Continue with the next product, or if every product is handled, thank the customer, say goodbye and call transition_to_wrap_up.'
    elif d is not None:
        d['what_to_do_next'] = 'The note was not recorded. CALL add_note once more with the same values.' if _count('note_failures') < 2 else 'The note could not be recorded. Continue without it.'
except Exception:
    pass
"""

TRANSFER_PRE = """F = __FIELDS__
try:
    b = config.get('body') if isinstance(config, dict) else None
    if isinstance(b, dict):
        vars['transfer_queue'] = str(b.get(F['queue']) or '')
except Exception:
    pass
"""

TRANSFER_POST = """import json
__COMMON__
F = __FIELDS__
try:
    d = _d(result)
    if d is not None and _ok(d, F):
        vars['transfer_state'] = 'done'
        d['what_to_do_next'] = 'Transfer requested. Tell the customer you are connecting them now, thank them and say goodbye.'
    elif d is not None:
        d['what_to_do_next'] = 'The transfer failed. CALL transfer_to_agent once more with the same queue.' if _count('transfer_failures') < 2 else 'The transfer could not be made now. Tell the customer so, thank them and say goodbye. Do not promise any call back.'
except Exception:
    pass
"""

CALLBACK_PRE = """__DATES_SRC__
import json, datetime, re
__COMMON__
CB = __CALLBACK__
WORDS = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11, 'twelve': 12, 'noon': 12, 'midday': 12, 'midnight': 0}
DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
def _day(text, today):
    t = translate(text).strip()
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
            if 'next' in t:                      # same arithmetic as the date engine: a weekday earlier in the week than today still lands next week
                return today + datetime.timedelta(days=7 - today.weekday() + i)
            return today + datetime.timedelta(days=(i - today.weekday()) % 7)
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
    t = translate(text).strip().replace('.', ':')
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
        pm = bool(m.group(3) and m.group(3).startswith('p')) or bool(re.search(r'\\bpm\\b', t))     # "pm" may come before the hour once translated
        am = bool(m.group(3) and m.group(3).startswith('a')) or bool(re.search(r'\\bam\\b', t))
        if pm and h < 12:
            h += 12
        if am and not pm and h == 12:
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
F = __FIELDS__
try:
    b = config.get('body') if isinstance(config, dict) else None
    vars['callback_block'] = ''
    if isinstance(b, dict) and (CB.get('days') or CB.get('from') or CB.get('to')):
        today = datetime.date.fromisoformat(str(vars.get('today'))[:10])
        nb = datetime.date.fromisoformat(str(vars.get('callback_next_business_day') or vars.get('next_business_day'))[:10])
        # an ISO date in the text would read as a time, so it is removed before the time is parsed
        day, t = _day(b.get(F['date']), today), _time(re.sub(r'\\d{4}-\\d{2}-\\d{2}', ' ', str(b.get(F['time']) or '') + ' ' + str(b.get(F['date']) or '')))
        now_t, days = str(vars.get('now_time') or ''), CB.get('days') or []
        frm, to = str(CB.get('from') or ''), str(CB.get('to') or '')
        ok_day = day is not None and ((day == today and 'today' in days) or (day == nb and 'next_business_day' in days))
        # a day outside the window is an offer outside it even when no time was said, so the ask counter moves instead of a clarifying question
        if day is None or (t is None and ok_day):
            vars['callback_block'] = 'NOT booked: the day or the time could not be read. CALL schedule_callback again with date as the day the person said (today, tomorrow, a weekday name, or YYYY-MM-DD) and time as they said it (for example 9pm or 10:30); today is ' + today.isoformat() + ' and the next business day is ' + nb.isoformat() + '. Do not ask the person for a date. If they gave no exact time, ask them for one inside the window first.'
            _block(b)
        else:
            b[F['date']], b[F['time']] = day.isoformat(), t or ''
            ok_time = t is not None and (not frm or t >= frm) and (not to or t <= to) and not (day == today and now_t and t <= now_t)
            if not (ok_day and ok_time):
                n = _count('callback_outside')
                limit = int(float(CB.get('max_asks') or 1))
                if n <= limit:
                    vars['callback_block'] = 'NOT booked: ' + day.isoformat() + (' at ' + t if t else '') + ' is outside the callback window (' + str(vars.get('callback_text') or '') + '). Ask for another day and time inside it, then CALL schedule_callback again.'
                else:
                    vars['callback_block'] = 'NOT booked: that is outside the window again. Do not book anything and do not ask again. Thank the person, say goodbye, and in the same message call transition_to_outcome_no_callback_quiet.'
                _block(b)
except Exception:
    pass
"""

CALLBACK_POST = """import json
__COMMON__
F = __FIELDS__
try:
    d = _d(result)
    block = str(vars.get('callback_block') or '')
    if d is None and isinstance(result, dict):
        result['data'] = d = dict()
    if block:
        vars['callback_block'] = ''
        if d is not None:
            d['what_to_do_next'] = block
    elif d is not None and _ok(d, F):
        vars['callback_state'] = 'done'
        d['what_to_do_next'] = 'Callback booked. Thank the person and say goodbye.'
    elif d is not None:
        d['what_to_do_next'] = 'The callback could not be booked. CALL schedule_callback once more with the same date and time.' if _count('callback_failures') < 2 else 'The callback could not be booked now. Tell the person so, thank them and say goodbye.'
except Exception:
    pass
"""

CLOSE_PRE = """__RECOMPUTE__
F = __FIELDS__
try:
    b = config.get('body') if isinstance(config, dict) else None
    NO_REASON = __NO_REASON__
    if isinstance(b, dict):
        o, r = str(vars.get('outcome') or ''), str(vars.get('reason') or '')
        if o:
            b[F['outcome']] = o
        elif not b.get(F['outcome']) or '{' in str(b.get(F['outcome'])):
            b[F['outcome']] = __DEFAULT_OUTCOME__
        if r:
            b[F['reason']] = r
        if b.get(F['outcome']) in NO_REASON or not b.get(F['reason']) or '{' in str(b.get(F['reason'])):
            b.pop(F['reason'], None)
except Exception:
    pass
"""


def all_hooks(policy, recompute="", dates_src="", fields=None):
    """Every hook's source, keyed by tool name and phase, filled from the policy and the API file's field names."""
    F = (fields or default_fields()).get
    ident, out = policy.get("identity") or {}, policy.get("outcomes") or {}
    default_outcome = (out.get("unclear") or {}).get("outcome", "")
    multi = (policy.get("multi_product") or {}).get("enabled")
    note_value = next((e.get("note_reason") for e in policy.get("end_reasons") or [] if e.get("key") == "service_error" and e.get("note_reason")), "")
    service_next = ("CALL add_note for this product with reason " + json.dumps(note_value) + ", then continue.") if (multi and note_value) else "Then continue with the other products, or thank the customer and say goodbye."
    return {
        ("verify_identity", "pre"): fill(VERIFY_PRE, dates_src=dates_src, common=COMMON, identity=ident, fields=F("verify_identity")), ("verify_identity", "post"): fill(VERIFY_POST, common=COMMON, identity=ident, fields=F("verify_identity")),
        ("create_promise", "pre"): fill(PROMISE_PRE, dates_src=dates_src, common=COMMON, cal=policy.get("calendar") or {}, adj=policy.get("date_adjust") or {}, fields=F("create_promise")),
        ("create_promise", "post"): fill(PROMISE_POST, common=COMMON, after_promise=json.dumps((policy.get("sentences") or {}).get("after_promise", "")), service_error_next=json.dumps(service_next), fields=F("create_promise")),
        ("add_note", "pre"): fill(NOTE_PRE, fields=F("add_note")), ("add_note", "post"): fill(NOTE_POST, common=COMMON, fields=F("add_note")),
        ("transfer_to_agent", "pre"): fill(TRANSFER_PRE, fields=F("transfer_to_agent")), ("transfer_to_agent", "post"): fill(TRANSFER_POST, common=COMMON, fields=F("transfer_to_agent")),
        ("schedule_callback", "pre"): fill(CALLBACK_PRE, dates_src=dates_src, common=COMMON, callback=policy.get("callback") or {}, fields=F("schedule_callback")), ("schedule_callback", "post"): fill(CALLBACK_POST, common=COMMON, fields=F("schedule_callback")),
        ("close_call", "pre"): fill(CLOSE_PRE, recompute=recompute or "", no_reason=policy.get("no_reason_outcomes") or [], default_outcome=json.dumps(default_outcome), fields=F("close_call")),
    }
