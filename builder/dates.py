"""Calendar facts from the call's `now` and the policy. Pure functions, stdlib only.

The same source runs inside Freya code steps (the renderer embeds this module), so it must import only
json, re and datetime, never raise on bad input, and never contain two braces in a row.
"""
import datetime

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
    return day.weekday() in cal.get("business_weekdays", [0, 1, 2, 3, 4]) and day.isoformat() not in set(cal.get("holidays", []))


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


def attempt1_date(today, cal):
    """Last business day of this week, or of next week when that day is today or already past."""
    d = last_business_day_of_week(today, cal)
    if d <= today:
        d = last_business_day_of_week(today + datetime.timedelta(days=7), cal)
    return d


def say(day):
    return day.strftime("%A %d %B %Y").replace(" 0", " ") + " (" + day.isoformat() + ")"


def weekday_table(today, cal):
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
    """Allowed callback days and times: today (if the window has not closed) and the next business day."""
    today = now.date()
    options = []
    if "today" in cb.get("days", ["today", "next_business_day"]):
        after = max(now.strftime("%H:%M"), cb.get("from", "10:00"))
        if after < cb.get("to", "19:00"):
            options.append("today, " + say(today) + ", from " + after + " to " + cb.get("to", "19:00"))
    nb = next_business_day(today, cal)
    options.append(say(nb) + ", from " + cb.get("from", "10:00") + " to " + cb.get("to", "19:00"))
    return {"next_business_day": nb.isoformat(), "text": " or ".join(options), "from": cb.get("from", "10:00"), "to": cb.get("to", "19:00")}


def calendar_facts(now_value, policy):
    """Variables for the prompts and routes that depend only on `now` and the policy."""
    now = parse_now(now_value) or datetime.datetime(2000, 1, 1, 9, 0)
    today, cal = now.date(), policy.get("calendar", {})
    bands = policy.get("bands", [])
    out = {
        "today": today.isoformat(), "today_text": say(today), "now_time": now.strftime("%H:%M"),
        "now_text": say(today) + " at " + now.strftime("%H:%M"),
        "next_business_day": next_business_day(today, cal).isoformat(),
        "attempt1_date": attempt1_date(today, cal).isoformat(), "attempt1_text": say(attempt1_date(today, cal)),
        "weekday_table": "\n".join(weekday_table(today, cal)),
    }
    for k, v in callback_window(now, cal, policy.get("callback", {})).items():
        out["callback_" + k] = v
    latest = today
    for b in bands:
        d = nth_business_day_after(today, int(b.get("deadline_business_days", 5)), cal)
        out["deadline_" + str(b.get("name", "band"))] = d.isoformat()
        latest = max(latest, d)
    out["business_days_text"] = "\n".join(say(d) for d in business_days_list(today, cal, latest))
    out["holidays_text"] = ", ".join(cal.get("holidays", [])) or "none"
    return out


def product_facts(products, policy, now_value):
    """Per-product band, deadline, floor, offers and words, plus a summary for the prompt."""
    now = parse_now(now_value) or datetime.datetime(2000, 1, 1, 9, 0)
    today, cal = now.date(), policy.get("calendar", {})
    words, floor_field = policy.get("product_words", {}), policy.get("floor_field", {})
    facts, lines = [], []
    for i, p in enumerate(products or []):
        ptype = str(p.get("type", ""))
        band = band_for(p.get("days_late"), policy.get("bands", []))
        deadline = nth_business_day_after(today, int(band.get("deadline_business_days", 5)), cal)
        floor = p.get(floor_field.get(ptype, ""), None)
        name = words.get(ptype, ptype.replace("_", " "))
        try:
            name = name.format(**{k: str(v) for k, v in p.items()})
        except (KeyError, IndexError, ValueError):
            pass
        f = {"product_id": str(p.get("product_id", "")), "type": ptype, "words": name, "past_due": p.get("past_due"),
             "days_late": p.get("days_late"), "band": band.get("name", ""), "attempts": int(band.get("attempts", 1)),
             "deadline": deadline.isoformat(), "floor": floor, "attempt1_date": attempt1_date(today, cal).isoformat()}
        facts.append(f)
        lines.append("Product " + str(i + 1) + ": id " + f["product_id"] + ", " + name + ", past due " + str(f["past_due"]) + ", " + str(f["days_late"])
                     + " days late, band " + f["band"] + ", floor amount " + str(floor) + ", latest promise date " + say(deadline)
                     + ", persuasion attempts allowed " + str(f["attempts"]) + ", attempt 1 date " + say(attempt1_date(today, cal)))
    return {"facts": facts, "summary": "\n".join(lines), "count": len(facts)}
