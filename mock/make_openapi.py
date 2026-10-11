"""Write mock/openapi.json for the final's services: paths and request fields from the route table, response shapes from the test customers' recorded answers.

    python3 mock/make_openapi.py <test-customers.json> <routes.json> mock/openapi.json

routes.json: [{"service", "method", "path", "lookup": [fields that pick the recorded answer], "fields": {name: description}, "summary", "fields": {name: description}}]
"""
import json, sys


def schema_of(value, name=""):
    """A JSON schema from one example value; the first item stands for a list; null becomes a nullable string."""
    if isinstance(value, dict):
        return {"type": "object", "properties": {k: schema_of(v, k) for k, v in value.items()}}
    if isinstance(value, list):
        return {"type": "array", "items": schema_of(value[0], name) if value else {"type": "string"}}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, (int, float)):
        return {"type": "number"}
    if value is None:
        return {"type": "string", "nullable": True}
    return {"type": "string"}


def merge(a, b):
    """The union of two schemas of the same shape, so that a field seen in any customer is listed."""
    if a.get("type") == "object" and b.get("type") == "object":
        props = dict(a["properties"])
        for k, v in b["properties"].items():
            props[k] = merge(props[k], v) if k in props else v
        return {"type": "object", "properties": props}
    if a.get("type") == "array" and b.get("type") == "array":
        return {"type": "array", "items": merge(a["items"], b["items"])}
    return a if a.get("type") != "string" or not a.get("nullable") else b


def examples(customers, service, depth):
    """Every recorded answer of one service across the customers, at the nesting depth of its keys."""
    out = []
    for c in customers:
        node = (c.get("services") or {}).get(service)
        if node is None:
            continue
        stack = [node]
        for _ in range(depth):
            stack = [v for n in stack for v in n.values() if isinstance(v, dict)]
        out += [n for n in stack if isinstance(n, dict) and "http" in n]
    return out


def main(customers_path, routes_path, out_path):
    customers = json.load(open(customers_path, encoding="utf-8"))
    customers = customers.get("customers", customers) if isinstance(customers, dict) else customers
    routes = json.load(open(routes_path, encoding="utf-8"))
    paths = {}
    for r in routes:
        answers = examples(customers, r["service"], len(r["lookup"]) - (1 if r["lookup"][0] == "customerNo" else 0))
        by_status = {}
        for a in answers:
            s = schema_of(a.get("response"))
            by_status[str(a["http"])] = merge(by_status[str(a["http"])], s) if str(a["http"]) in by_status else s
        fields = r.get("fields") or {k: "" for k in r["lookup"]}
        error_shape = next((by_status[k] for k in by_status if k != "200"), {"type": "object", "properties": {"result": {"type": "object"}}})
        for status in r.get("statuses") or {}:                       # the contract's error answers the recordings happen not to show
            by_status.setdefault(status, error_shape)
        request = {"type": "object", "required": ["data"], "properties": {
            "data": {"type": "object", "properties": {k: {"type": "string", "description": d} for k, d in fields.items()}, "required": list(fields)},
            "call": {"type": "object", "description": "call metadata the bank logs; not checked in test", "properties": {"ani": {"type": "string", "description": "the caller's number"}, "lang": {"type": "string", "description": "tr"}}}}}
        op = {"operationId": r["service"].replace(".", "_"), "summary": r.get("summary", r["service"]), "description": r.get("description", ""),
              "requestBody": {"required": True, "content": {"application/json": {"schema": request}}},
              "responses": {status: {"description": r.get("statuses", {}).get(status, "as recorded for the test customers"), "content": {"application/json": {"schema": schema}}} for status, schema in sorted(by_status.items())}}
        paths[r["path"]] = {r.get("method", "POST").lower(): op}
    doc = {"openapi": "3.0.3", "info": {"title": "Freya Bank voice services: statement and debt (the bank's test environment, mocked)", "version": "1.0.0",
                                        "description": "Every service is POST with a JSON body {data: {...}, call: {ani, lang}}; every answer has a result object (returnCode 1 and HTTP 200 mean success) and successful answers also have data. Error answers have only result (type ERROR or WARNING, code and message). Dates are dd.MM.yyyy strings, amounts JSON numbers. Always send cardNumber exactly as cards.list returned it."},
           "servers": [{"url": "https://bank-mock.bank-mock.workers.dev/voice/v1"}], "paths": paths}
    json.dump(doc, open(out_path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("openapi:", len(paths), "paths;", ", ".join(p + " " + "/".join(sorted(paths[p][m]["responses"])) for p in paths for m in paths[p]))


if __name__ == "__main__":
    main(*sys.argv[1:4])
