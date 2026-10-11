"""Calendar facts from the call's `now` and the policy. Pure functions, stdlib only.

The same source runs inside Freya code steps (the renderer embeds this module), so it must import only
json, re and datetime, never raise on bad input, never contain two braces in a row, and hold no bank's values.
"""
import datetime
import re

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def parse_now(value):
    """`now` as a datetime. Accepts 2026-10-14T11:00, with seconds, or with a trailing Z."""
    s = str(value or "").strip().replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(s[:19], fmt)
        except ValueError:
            pass
    return None


def is_business_day(day, cal):
    return day.weekday() in (cal.get("business_weekdays") or [0, 1, 2, 3, 4]) and day.isoformat() not in set(cal.get("holidays") or [])


def next_business_day(day, cal, include_today=False):
    d = day if include_today else day + datetime.timedelta(days=1)
    for _ in range(60):
        if is_business_day(d, cal):
            return d
        d += datetime.timedelta(days=1)
    return day


def nth_business_day_after(day, n, cal):
    d, count = day, 0
    for _ in range(400):
        d += datetime.timedelta(days=1)
        if is_business_day(d, cal):
            count += 1
            if count >= n:
                return d
    return d


def last_business_day_of_week(day, cal):
    """Last business day of the Monday-to-Sunday week that holds `day`."""
    sunday = day + datetime.timedelta(days=6 - day.weekday())
    d = sunday
    for _ in range(7):
        if is_business_day(d, cal):
            return d
        d -= datetime.timedelta(days=1)
    return sunday


def attempt1_date(today, cal, rule):
    """The date the first persuasion attempt proposes, by the policy's rule. None when the policy gives none."""
    kind, n = str((rule or {}).get("rule") or ""), int(float((rule or {}).get("n") or 0))
    if kind == "last_business_day_of_week":
        d = last_business_day_of_week(today, cal)
        return d if d > today else last_business_day_of_week(today + datetime.timedelta(days=7), cal)
    if kind == "next_business_day":
        return next_business_day(today, cal)
    if kind == "nth_business_day":
        return nth_business_day_after(today, max(n, 1), cal)
    return None


MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]


def parse_day_words(text, today):
    """A day said in words, as a date, or None. A bare or "this" weekday is its next occurrence, today included; "next <weekday>" is the one in
    the week after; a weekday with a day number is the next date that is both."""
    t = " " + str(text or "").strip().lower().replace(",", " ") + " "
    if not t.strip():
        return None
    # a time of day is not a day number
    t = re.sub(r"\bat \d{1,2}(:\d{2})?\s*(am|pm)?|\b\d{1,2}:\d{2}\b|\b\d{1,2}\s*(am|pm)\b", " ", t)
    digits = [int(x) for x in re.findall(r"\d+", t)]
    if len(digits) >= 3 and "-" in t and digits[0] > 1900:
        try:
            return datetime.date(digits[0], digits[1], digits[2])
        except ValueError:
            return None
    if " today " in t or " tonight " in t or " this evening " in t or " this afternoon " in t or " this morning " in t:
        return today
    if " day after tomorrow " in t:
        return today + datetime.timedelta(days=2)
    if " tomorrow " in t:
        return today + datetime.timedelta(days=1)
    month = next((k + 1 for k, m in enumerate(MONTHS) if " " + m + " " in t or " " + m[:3] + " " in t), None)
    day = next((d for d in digits if 1 <= d <= 31), None)
    weekday = next((i for i, name in enumerate(WEEKDAYS) if " " + name.lower() + " " in t or " " + name.lower()[:3] + " " in t), None)
    if weekday is not None and not (month and day):
        return _weekday_date(weekday, day, today, " next " in t)
    if day:
        try:
            cand = datetime.date(today.year, month or today.month, day)
            if cand < today and not month:
                cand = datetime.date(today.year + (1 if today.month == 12 else 0), today.month % 12 + 1, day)
            elif cand < today:
                cand = datetime.date(today.year + 1, month, day)
            return cand
        except ValueError:
            return None
    return None


def _weekday_date(weekday, day, today, is_next):
    """A weekday with a day number ("Monday 2") is the next date that is both, as when the customer accepts a date the agent offered;
    a bare or "this" weekday, or a pair that never matches within two months, is the next occurrence, today included; "next" is the week after."""
    for n in range(62 if day else 0):
        cand = today + datetime.timedelta(days=n)
        if cand.day == day and cand.weekday() == weekday:
            return cand
    if is_next:                                      # a weekday earlier in the week than today still lands in the week after, not two weeks on
        return today + datetime.timedelta(days=7 - today.weekday() + weekday)
    return today + datetime.timedelta(days=(weekday - today.weekday()) % 7)


def adjust_day(day, today, deadline, cal, rules):
    """(date to use, reason) for a proposed day under the policy's date_adjust rules; reason is empty when the day stands."""
    nb, ad = str((rules or {}).get("non_business_day") or ""), str((rules or {}).get("after_deadline") or "")
    if day < today:
        return today, "is in the past; the earliest date is today"
    if day > deadline:
        return (deadline, "is after the latest allowed date; say the latest date you can record is " + say(deadline) + " and offer it") if ad == "offer_deadline" else (None, "is after the latest allowed date; follow your instructions")
    if not is_business_day(day, cal):
        if nb == "next_business_day":
            d = next_business_day(day, cal)
            return (d, "is not a business day; offer " + say(d) + " instead") if d <= deadline else (deadline, "is not a business day and the next business day is after the latest allowed date; offer " + say(deadline))
        if nb == "previous_business_day":
            d = day
            while not is_business_day(d, cal) and d > today:
                d -= datetime.timedelta(days=1)
            return d, "is not a business day; offer " + say(d) + " instead"
        return None, "is not a business day; follow your instructions"
    return day, ""


def date_parts(text, numeric_order="day_month_year"):
    """The day, month and year found in a date answer, None for each part that is missing.

    The dialogue model sends a date said without a year as a partial ISO form such as 0003-03-14 or -03-14, so that shape
    gives month and day only; the year must be four digits."""
    t = " " + str(text or "").strip().lower().replace(",", " ") + " "
    iso = re.search(r"(?<!\d)(\d{4}|)-(\d{1,2})-(\d{1,2})(?!\d)", t)
    year = next((int(n) for n in re.findall(r"\d{4}", t) if 1900 <= int(n) <= 2100), None)
    if iso:
        return {"day": int(iso.group(3)) or None, "month": int(iso.group(2)) or None, "year": year}
    t = t.replace("/", " ").replace(".", " ").replace("-", " ")
    nums = [int(x) for x in re.findall(r"\d+", t)]
    month = next((k + 1 for k, m in enumerate(MONTHS) if " " + m + " " in t or " " + m[:3] + " " in t), None)
    small = [n for n in nums if n != year and 1 <= n <= 31]
    ordinal = re.findall(r"\b(\d{1,2})(?:st|nd|rd|th)\b", t)
    day = None
    if month is None and len(small) >= 2:
        first, second = small[0], small[1]
        day, month = (first, second) if numeric_order == "day_month_year" else (second, first)
        if month > 12 and day <= 12:
            day, month = month, day
    elif small:
        day = int(ordinal[0]) if ordinal else small[0]
    return {"day": day, "month": month, "year": year}


def parse_full_date(text, numeric_order="day_month_year"):
    """A complete date of birth style answer (day, month and a four-digit year) as a date, or None when any part is missing."""
    p = date_parts(text, numeric_order)
    if None in p.values():
        return None
    try:
        return datetime.date(p["year"], p["month"], p["day"])
    except ValueError:
        return None


def say(day):
    return day.strftime("%A %d %B %Y").replace(" 0", " ") + " (" + day.isoformat() + ")"


def money(x):
    try:
        v = float(x)
        return str(int(v)) if v == int(v) else ("%.2f" % v)
    except (TypeError, ValueError):
        return str(x)


def weekday_table(today):
    """Lines for "this <weekday>" (current week) and "next <weekday>" (following calendar week)."""
    monday = today - datetime.timedelta(days=today.weekday())
    lines = []
    for i, name in enumerate(WEEKDAYS):
        this_day = monday + datetime.timedelta(days=i)
        next_day = this_day + datetime.timedelta(days=7)
        note = " (already passed)" if this_day < today else (" (today)" if this_day == today else "")
        lines.append("this " + name + " = " + this_day.isoformat() + note + "; next " + name + " = " + next_day.isoformat())
    return lines


def business_days_list(today, cal, until):
    days, d = [], today
    while d <= until and len(days) < 60:
        if is_business_day(d, cal):
            days.append(d)
        d += datetime.timedelta(days=1)
    return days


def band_for(days_late, bands):
    try:
        n = int(float(days_late))
    except (TypeError, ValueError):
        return bands[-1] if bands else {}
    for b in bands:
        if int(b.get("days_late_min", 0)) <= n <= int(b.get("days_late_max", 10 ** 6)):
            return b
    return bands[-1] if bands else {}


def callback_window(now, cal, cb):
    """Allowed callback days and times from the policy. Empty text when the policy gives no window."""
    today, days, frm, to = now.date(), cb.get("days") or [], str(cb.get("from") or ""), str(cb.get("to") or "")
    nb = next_business_day(today, cal)
    options = []
    if "today" in days and frm and to:
        after = max(now.strftime("%H:%M"), frm)
        if after < to:
            options.append("today, " + say(today) + ", from " + after + " to " + to)
    if "next_business_day" in days:
        options.append(say(nb) + (", from " + frm + " to " + to if frm and to else ""))
    return {"next_business_day": nb.isoformat(), "text": " or ".join(options) or "no callback window is given in your instructions", "from": frm, "to": to}


def calendar_facts(now_value, policy):
    """Variables for the prompts and routes that depend only on `now` and the policy."""
    now = parse_now(now_value) or datetime.datetime(2000, 1, 1, 9, 0)
    today, cal = now.date(), policy.get("calendar") or {}
    a1 = attempt1_date(today, cal, policy.get("attempt1_rule"))
    out = {
        "today": today.isoformat(), "today_text": say(today), "now_time": now.strftime("%H:%M"),
        "now_text": say(today) + " at " + now.strftime("%H:%M"),
        "next_business_day": next_business_day(today, cal).isoformat(),
        "attempt1_date": a1.isoformat() if a1 else "", "attempt1_text": say(a1) if a1 else "the latest allowed date of the product",
        "weekday_table": "\n".join(weekday_table(today)),
    }
    for k, v in callback_window(now, cal, policy.get("callback") or {}).items():
        out["callback_" + k] = v
    latest = today
    for b in policy.get("bands") or []:
        d = nth_business_day_after(today, int(b.get("deadline_business_days", 5)), cal)
        out["deadline_" + str(b.get("name", "band"))] = d.isoformat()
        latest = max(latest, d)
    out["business_days_text"] = "\n".join(say(d) for d in business_days_list(today, cal, latest))
    skipped, d = [], today
    while d <= latest and len(skipped) < 40:
        if not is_business_day(d, cal):
            skipped.append(say(d) + " is not a business day; the next business day is " + say(next_business_day(d, cal)))
        d += datetime.timedelta(days=1)
    out["non_business_days_text"] = "\n".join(skipped) or "none before the latest allowed date"
    out["holidays_text"] = ", ".join(cal.get("holidays") or []) or "none"
    return out


def product_facts(products, policy, now_value):
    """Per-product band, deadline, floor, offers and words, plus a summary and a spoken debt statement."""
    now = parse_now(now_value) or datetime.datetime(2000, 1, 1, 9, 0)
    today, cal = now.date(), policy.get("calendar") or {}
    words, floor_field = policy.get("product_words") or {}, policy.get("floor_field") or {}
    rule = policy.get("attempt1_rule") or {}
    a1 = attempt1_date(today, cal, rule)
    facts, lines, spoken = [], [], []
    for i, p in enumerate(products or []):
        ptype = str(p.get("type", ""))
        band = band_for(p.get("days_late"), policy.get("bands") or [])
        deadline = nth_business_day_after(today, int(band.get("deadline_business_days", 5)), cal)
        floor = p.get(floor_field.get(ptype, ""), None)
        name = words.get(ptype, ptype.replace("_", " "))
        try:
            name = name.format(**{k: str(v) for k, v in p.items()})
        except (KeyError, IndexError, ValueError):
            pass
        first = deadline if str(rule.get("rule")) == "deadline" else a1
        f = {"product_id": str(p.get("product_id", "")), "type": ptype, "words": name, "past_due": p.get("past_due"),
             "days_late": p.get("days_late"), "band": band.get("name", ""), "attempts": int(band.get("attempts", 1)),
             "deadline": deadline.isoformat(), "floor": floor, "attempt1_date": first.isoformat() if first else ""}
        facts.append(f)
        attempts = f["attempts"]
        if attempts <= 0:
            offers = "no persuasion attempt: after a refusal, stop, thank the customer and say goodbye"
        elif attempts == 1:
            offers = ("one persuasion attempt only: after a flat refusal propose " + (say(first) if first else "the latest allowed date") + " for the amount in play; if that is refused too, STOP: make no further offer of any amount or date, thank the customer and say goodbye")
        else:
            offers = ("persuasion attempts: after a flat refusal propose " + (say(first) if first else "the latest allowed date") + " for the amount in play; after a second flat refusal propose the floor amount " + money(floor) + " on " + say(deadline)
                      + "; after that STOP: make no further offer, thank the customer and say goodbye")
        lines.append("Product " + str(i + 1) + ": id " + f["product_id"] + ", " + name + ", past due " + money(f["past_due"]) + ", " + str(f["days_late"])
                     + " days late, band " + f["band"] + ", floor amount " + money(floor) + ", latest allowed date " + say(deadline)
                     + " (propose this when the customer gives a vague period and no exact day, or asks for a later date); " + offers + ".")
        spoken.append("Your " + name + " is " + money(f["past_due"]) + " past due and " + str(f["days_late"]) + " days late.")
    return {"facts": facts, "summary": "\n".join(lines), "count": len(facts), "spoken": " ".join(spoken)}
