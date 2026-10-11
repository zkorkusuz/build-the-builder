"""Check the deployed final mock against the bank's test customers: every recorded answer must come back with its status and body.

    python3 mock/check_final.py https://<worker>.workers.dev mock/customers.json <routes.json> [customerNo ...]

Reads the served /openapi.json (paths must match the route table), calls every service of each listed customer (all when none is
given) with the keys the data was recorded under, compares status and body with the recording, then prints the ledger of the first.
"""
import json, sys, time, urllib.error, urllib.request

UA = {"content-type": "application/json", "User-Agent": "Mozilla/5.0 build-the-builder"}


def http(url, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw[:200]


def answers(node, keys, values=()):
    """(key values, recorded answer) pairs under one service entry, descending the nesting of its keys."""
    if "http" in node:
        return [(values, node)]
    out = []
    for k, v in node.items():
        if isinstance(v, dict):
            out += answers(v, keys, values + (k,))
    return out


def main(argv):
    base, customers_path, routes_path, only = argv[0].rstrip("/"), argv[1], argv[2], argv[3:]
    status, spec = http(base + "/openapi.json")
    paths = list((spec or {}).get("paths") or {}) if isinstance(spec, dict) else []
    server = (spec.get("servers") or [{}])[0].get("url") if isinstance(spec, dict) else base
    routes = json.load(open(routes_path, encoding="utf-8"))
    print("openapi:", status, len(paths), "paths | servers", server, "| routes missing from it:", [r["path"] for r in routes if r["path"] not in paths] or "none")
    data = json.load(open(customers_path, encoding="utf-8"))
    customers = [c for c in data["customers"] if not only or c["customerNo"] in only]
    ok = bad = 0
    for c in customers:
        for r in routes:
            entry = (c.get("services") or {}).get(r["service"])
            if entry is None:
                continue
            for values, rec in answers(entry, r["lookup"]):
                data = {k: "1" if k == "statementDay" else "E" if k == "intAddressInfoType" else "x" for k in (r.get("fields") or {})}   # the mock checks presence, not values
                data.update({"customerNo": c["customerNo"]} if r["lookup"][0] == "customerNo" else {})
                data.update(dict(zip([k for k in r["lookup"] if k != "customerNo"], values)))
                t0 = time.time()
                st, out = http(server + r["path"], {"data": data, "call": {"ani": "", "lang": "tr"}})
                want = rec.get("response", rec.get("yanit"))
                good = st == rec["http"] and out == want
                ok += good; bad += not good
                if not good or only:
                    print(("ok  " if good else "BAD "), c["customerNo"], r["service"], values, "->", st, "(want", rec["http"], ")", str(round(time.time() - t0, 1)) + "s", "" if good else json.dumps(out, ensure_ascii=False)[:200])
    print("\nanswers:", ok, "match,", bad, "differ")
    if customers:
        st, led = http(base + "/ledger/" + customers[0]["customerNo"])
        print("ledger of", customers[0]["customerNo"] + ":", json.dumps(led, ensure_ascii=False)[:800])


if __name__ == "__main__":
    main(sys.argv[1:] or sys.exit(__doc__))
