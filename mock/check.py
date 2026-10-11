"""Call every tool of the deployed mock once, in the order of a call, and print what the bank recorded.

    python3 mock/check.py https://<worker>.<subdomain>.workers.dev [case id]

Reads <url>/openapi.json for the paths and request fields, opens a session for the case (the first customer in
mock/customers.json when none is given; a customer with a fixed customer_id needs no session), posts to every path with
a body built from the schema and the customer's own answers and products, prints each status and answer, then the ledger.
A path, field name or enum value that does not match the contract shows up as ok:false, 404 or an empty ledger list
here, before a build spends a model call. Needs `source env` for the practice routes' team key.
"""
import datetime, json, os, pathlib, sys, urllib.error, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
ORDER = ["verify_identity", "get_account", "create_promise", "add_note", "schedule_callback", "transfer_to_agent", "close_call"]


def http(url, body=None):
    headers = {"content-type": "application/json", "User-Agent": "Mozilla/5.0 build-the-builder", "X-Team-Key": os.environ.get("FREYA_BANK_TEAM_KEY", "")}   # without a browser User-Agent Cloudflare answers 403 (error 1010)
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, parse(r.read())
    except urllib.error.HTTPError as e:
        return e.code, parse(e.read())


def parse(raw):
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError:
        return raw.decode("utf-8", errors="replace")[:200]


def properties(spec, path):
    op = (spec["paths"].get(path) or {}).get("post") or {}
    schema = (((op.get("requestBody") or {}).get("content") or {}).get("application/json") or {}).get("schema") or {}
    if "$ref" in schema:
        node = spec
        for part in schema["$ref"][2:].split("/"):
            node = node.get(part) or {}
        schema = node
    return schema.get("properties") or {}


def value(name, prop, ctx):
    """A plausible value for one request field, by its name: the customer's own ids and amounts, tomorrow, a time, the first enum value."""
    n = name.lower()
    if n == "customer_id":
        return ctx["cid"]
    if "product" in n or n.endswith("_id"):
        return ctx.get("product_id", "p1")
    if any(w in n for w in ("amount", "sum", "total", "value")):
        return ctx.get("amount", 1)
    if "date" in n or "day" in n or "when" in n:
        return ctx["tomorrow"]
    if "time" in n or "hour" in n or "slot" in n:
        return "10:30"
    if prop.get("enum"):
        return prop["enum"][0]
    if prop.get("type") == "number" or prop.get("type") == "integer":
        return 1
    return "check"


def call(server, path, body):
    status, out = http(server + path, body)
    print("POST " + path + " " + json.dumps({k: v for k, v in body.items() if k != "customer_id"}, ensure_ascii=False) + " -> " + str(status) + " " + json.dumps(out, ensure_ascii=False)[:300])
    if status >= 500:                                        # a fail_first customer answers 500 once; the agent's tools retry, so does this
        status, out = http(server + path, body)
        print("  again -> " + str(status) + " " + json.dumps(out, ensure_ascii=False)[:300])
    return out if isinstance(out, dict) else {}


def open_case(server, case_id):
    """The customer to play (the named one, else the first in customers.json) and its customer_id: fixed in the file, or from a new session."""
    cases = json.loads((ROOT / "customers.json").read_text())
    cases = cases.get("cases", []) if isinstance(cases, dict) else cases
    case = next((c for c in cases if c.get("id") == case_id), None) if case_id else cases[0]
    if case is None:
        sys.exit("no case " + str(case_id) + " in mock/customers.json; ids: " + ", ".join(str(c.get("id")) for c in cases))
    cid = case.get("customer_id")
    if not cid:
        status, session = http(server + "/practice/sessions", {"case": case["id"]})
        cid = ((session or {}).get("variables") or {}).get("customer_id") if isinstance(session, dict) else None
        if not cid:
            sys.exit("could not open a session for " + str(case["id"]) + ": " + str(status) + " " + str(session)[:200])
    print("case " + str(case["id"]) + " customer_id " + cid + (" (fixed)" if case.get("customer_id") else " (session)"))
    return case, cid


def main(argv):
    base = argv[0].rstrip("/")
    base = base if "://" in base else "https://" + base
    status, spec = http(base + "/openapi.json")
    if status != 200 or not isinstance(spec, dict) or not spec.get("paths"):
        sys.exit("no OpenAPI at " + base + "/openapi.json: " + str(status) + " " + str(spec)[:200])
    server = (spec.get("servers") or [{}])[0].get("url") or base
    print("openapi: " + str(len(spec["paths"])) + " paths " + ", ".join(spec["paths"]) + " | servers " + server)
    case, cid = open_case(server, argv[1] if len(argv) > 1 else None)
    ctx = {"cid": cid, "tomorrow": (datetime.date.today() + datetime.timedelta(days=1)).isoformat()}
    for name in ORDER:
        path = next((p for p in spec["paths"] if p.rstrip("/").endswith("/" + name)), None)
        if path is None:
            print("no path for " + name + " in the OpenAPI"); continue
        props = properties(spec, path)
        if name == "verify_identity":
            field_prop = next((p for p in props if p != "customer_id" and (props[p].get("enum") or "field" in p or "question" in p or "type" in p)), None)
            answer_prop = next((p for p in props if p not in ("customer_id", field_prop)), None)
            if field_prop is None or answer_prop is None:
                sys.exit("verify_identity needs a field and an answer property; the OpenAPI lists " + ", ".join(props))
            for field, answer in (case.get("identity") or {}).items():
                call(server, path, {"customer_id": cid, field_prop: field, answer_prop: str(answer)})
            continue
        out = call(server, path, {k: value(k, v, ctx) for k, v in props.items()})
        if name == "get_account":
            products = next((v for v in out.values() if isinstance(v, list)), [])
            if products:
                ctx["product_id"] = next((v for k, v in products[0].items() if "id" in k.lower()), "p1")
                ctx["amount"] = next((v for k, v in products[0].items() if any(w in k.lower() for w in ("past", "due", "overdue", "balance", "amount"))), 1)
    status, ledger = http(server + "/practice/ledger/" + cid)
    if not isinstance(ledger, dict):
        sys.exit("ledger: " + str(status) + " " + str(ledger)[:200])
    counts = ", ".join(k + " " + str(len(v)) for k, v in ledger.items() if isinstance(v, list))
    print("ledger: " + counts + " | outcome " + str(ledger.get("outcome")) + " reason " + str(ledger.get("reason")) + " | verified " + json.dumps(ledger.get("verified")))
    print(json.dumps(ledger, ensure_ascii=False, indent=1)[:1500])


if __name__ == "__main__":
    main(sys.argv[1:] or sys.exit(__doc__))
