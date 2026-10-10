"""Render the extra cases for another calendar day: expected dates and the dates named in scripts and checks follow `now`.

    .venv/bin/python tests/day_cases.py 2026-10-16T11:00 results/cases-fri.json      # then: run_cases.py <agent> --cases results/cases-fri.json --now 2026-10-16T11:00

Cases carry a `date_rule` for their expected promise or callback date (today, attempt1, deadline, next_friday, next_bd, fixed, none)
and may use tokens in text: {today_say} {attempt1_say} {deadline_say} {next_friday_say} {next_bd_say}. A case with `fixed_dates`
earlier than `now` is dropped. The date engine is the one the agent uses, so check a few dates by hand against the brief.
"""
import datetime, json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from builder import dates

POLICY = json.loads((ROOT / "tests" / "fixtures" / "policy-a.json").read_text())


def tokens(now, products):
    """Token values for one case's customer: the band comes from its first product."""
    today = dates.parse_now(now).date()
    cal = POLICY["calendar"]
    band = dates.band_for(products[0]["days_late"], POLICY["bands"])
    deadline = dates.nth_business_day_after(today, band["deadline_business_days"], cal)
    a1 = dates.attempt1_date(today, cal, POLICY["attempt1_rule"])
    next_friday = today - datetime.timedelta(days=today.weekday()) + datetime.timedelta(days=4 + 7)
    nb = dates.next_business_day(today, cal)
    say = lambda d: d.strftime("%A %d %B").replace(" 0", " ")
    short = lambda d: d.strftime("%d %B").lstrip("0")
    return {"today_iso": today.isoformat(), "attempt1_iso": a1.isoformat(), "deadline_iso": deadline.isoformat(), "next_friday_iso": next_friday.isoformat(), "next_bd_iso": nb.isoformat(),
            "today_say": short(today), "attempt1_say": say(a1), "deadline_say": short(deadline), "next_friday_say": say(next_friday), "next_bd_say": say(nb)}


def render(cases, now):
    out, today = [], dates.parse_now(now).date()
    for c in cases:
        c = json.loads(json.dumps(c))
        if any(datetime.date.fromisoformat(d) < today for d in c.get("fixed_dates", [])):
            continue
        t = tokens(now, c["products"])
        fill = lambda s: s.format(**t) if isinstance(s, str) else s
        c["title"], c["script"], c["checks"] = fill(c["title"]), fill(c["script"]), [fill(x) for x in c["checks"]]
        rule = c.pop("date_rule", "none")
        if rule != "none" and rule != "fixed":
            key = {"today": "today_iso", "attempt1": "attempt1_iso", "deadline": "deadline_iso", "next_friday": "next_friday_iso", "next_bd": "next_bd_iso"}[rule]
            for p in c["expected"]["promises"]:
                p["date"] = t[key]
            for cb in c["expected"]["callbacks"]:
                cb["date"] = t[key]
        c.pop("fixed_dates", None)
        c["variables"] = dict(c["variables"], now=now)
        out.append(c)
    return out


if __name__ == "__main__":
    now, target = sys.argv[1], sys.argv[2]
    src = json.loads((ROOT / "tests" / "extra-cases.json").read_text())
    pub = json.loads((ROOT / "public-test-set.json").read_text())
    base = [dict(c, date_rule={"PUB-01": "today", "PUB-02": "next_bd"}.get(c["id"], "none")) for c in pub if c["id"] in ("PUB-01", "PUB-02", "PUB-03")]
    cases = render(base + src, now)
    json.dump(cases, open(target, "w"), indent=1)
    print(len(cases), "cases for now =", now, "->", target)
