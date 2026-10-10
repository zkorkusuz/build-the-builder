"""Generalization check: run the normalize stage on a variant brief folder and compare the structured fields with expected.json.

    .venv/bin/python tests/check_variant.py tests/variants/v1        (one builder model call)
"""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from builder import llm, normalize


def flat(policy):
    """The same shape as expected.json, taken from a policy."""
    g = lambda *ks: _dig(policy, ks)
    return {
        "callback": {k: g("callback", k) for k in ("days", "from", "to")},
        "identity.questions.fields": [q.get("field") for q in g("identity", "questions") or []], "identity.max_wrong_total": g("identity", "max_wrong_total"), "identity.hint_value": g("identity", "hint_value") or "",
        "calendar.holidays": sorted(g("calendar", "holidays") or []),
        "bands": [{k: b.get(k) for k in ("days_late_min", "days_late_max", "deadline_business_days", "attempts")} for b in g("bands") or []],
        "attempt1_rule.rule": g("attempt1_rule", "rule"),
        "outcomes": {k: [v.get("outcome"), v.get("reason") or ""] for k, v in (g("outcomes") or {}).items()},
        "end_reasons": {e.get("key"): [e.get("outcome"), e.get("reason") or ""] for e in g("end_reasons") or []},
        "transfers": {t.get("queue"): [t.get("outcome"), t.get("reason") or ""] for t in g("transfers") or []},
        "no_reason_outcomes": sorted(g("no_reason_outcomes") or []),
        "sentences.after_promise": g("sentences", "after_promise"), "sentences.first_ask": g("sentences", "first_ask"), "sentences.confirm_question": g("sentences", "confirm_question"),
        "third_party.deceased_sentence": g("third_party", "deceased_sentence"), "multi_product.enabled": g("multi_product", "enabled"),
    }


def _dig(d, keys):
    for k in keys:
        d = d.get(k) if isinstance(d, dict) else None
    return d


def main(folder):
    folder = pathlib.Path(folder)
    briefs = [(p.name, p.read_text()) for p in sorted(folder.glob("*.md"))]
    spec = (folder / "openapi.json").read_text()
    lines = []
    policy = normalize.normalize(briefs, spec, folder, lines.append, llm.ask, llm.parse_json)
    (folder / "policy.out.json").write_text(json.dumps(policy, indent=1))
    got, exp = flat(policy), json.loads((folder / "expected.json").read_text())
    exp["no_reason_outcomes"] = sorted(exp["no_reason_outcomes"]); exp["calendar.holidays"] = sorted(exp["calendar.holidays"])
    same = lambda k: all(got.get(k, {}).get(x) == v for x, v in exp[k].items()) if k in ("outcomes", "end_reasons", "transfers") else got.get(k) == exp[k]
    bad = [k for k in exp if not same(k)]            # a keyed map may hold extra keys the brief defines; every expected key must match
    for k in bad:
        print("DIFF", k, "\n   got:     ", json.dumps(got.get(k))[:300], "\n   expected:", json.dumps(exp[k])[:300])
    print("\n".join(lines))
    print(str(len(exp) - len(bad)) + " / " + str(len(exp)) + " fields match; rules extracted:", len(policy.get("rules", [])))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
