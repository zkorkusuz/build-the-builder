"""The tool API file's field names by role, so hooks, routes and the product facts follow the bank's spelling, not the practice file's."""
# Each tool's request and response fields by role, with the words that find a renamed field in an API file that the policy did not map:
# (where, keywords). Hooks read names through F, so a bank that calls the amount "sum" or the products "accounts" still works.
FIELD_ROLES = {
    "verify_identity": {"field": ("request", ["field", "question", "type"]), "answer": ("request", ["answer", "value", "response"]), "ok": ("response", ["ok", "success"]),
                        "error": ("response", ["error", "message"]), "all_verified": ("response", ["all", "fully", "complete"]), "verified": ("response", ["verified", "correct", "match", "pass"]),
                        "wrong_answers_left": ("response", ["left", "remaining"]), "hint": ("response", ["hint"])},
    "get_account": {"ok": ("response", ["ok", "success"]), "error": ("response", ["error", "message"]), "products": ("response", ["product", "account", "item", "debt", "loan"]),
                    "product_id": ("product", ["id", "ref"]), "type": ("product", ["type", "kind"]), "past_due": ("product", ["past", "due", "overdue", "arrears", "balance"]), "days_late": ("product", ["day", "late"])},
    "create_promise": {"product_id": ("request", ["product", "account", "id"]), "amount": ("request", ["amount", "sum", "value", "total"]), "date": ("request", ["date", "day", "when"]),
                       "ok": ("response", ["ok", "success"]), "error": ("response", ["error", "message"])},
    "add_note": {"product_id": ("request", ["product", "account", "id"]), "reason": ("request", ["reason", "why", "code"]), "text": ("request", ["text", "note", "comment"]),
                 "ok": ("response", ["ok", "success"]), "error": ("response", ["error", "message"])},
    "schedule_callback": {"date": ("request", ["date", "day", "when"]), "time": ("request", ["time", "hour", "slot"]), "ok": ("response", ["ok", "success"]), "error": ("response", ["error", "message"])},
    "transfer_to_agent": {"queue": ("request", ["queue", "team", "department"]), "ok": ("response", ["ok", "success"]), "error": ("response", ["error", "message"])},
    "close_call": {"outcome": ("request", ["outcome", "result", "status"]), "reason": ("request", ["reason", "why", "code"]), "ok": ("response", ["ok", "success"]), "error": ("response", ["error", "message"])},
}


def default_fields():
    """The role names themselves, the practice API's spelling."""
    return {t: {r: r for r in roles} for t, roles in FIELD_ROLES.items()}


def find_path(spec, name):
    """The API file's path for a tool: exact, or the one that ends with the tool name, with its POST (or only) operation."""
    paths = spec.get("paths") or {}
    key = "/" + name if "/" + name in paths else next((k for k in paths if k.rstrip("/").endswith("/" + name)), "/" + name)
    item = paths.get(key) or {}
    return key, item.get("post") or next((v for v in item.values() if isinstance(v, dict)), {})


def deref(spec, schema):
    """A schema with a $ref replaced by its target under the file's own components."""
    ref = (schema or {}).get("$ref") if isinstance(schema, dict) else None
    if ref and ref.startswith("#/"):
        node = spec
        for part in ref[2:].split("/"):
            node = (node or {}).get(part) or {}
        return node
    return schema or {}


def _properties(spec, op, part):
    body = (op.get("requestBody") or {}) if part == "request" else ((op.get("responses") or {}).get("200") or {})
    schema = deref(spec, ((body.get("content") or {}).get("application/json") or {}).get("schema") or {})
    return {k: deref(spec, v) for k, v in (schema.get("properties") or {}).items()}


def field_names(policy, spec):
    """Each tool's field names by role: the policy's api_fields when the API file has that name, else the role name itself,
    else the first field whose name contains one of the role's keywords. Hooks, routes and the product facts all read names from here."""
    out = {}
    for tool_name, roles in FIELD_ROLES.items():
        op = find_path(spec, tool_name)[1]
        have = {"request": _properties(spec, op, "request"), "response": _properties(spec, op, "response")}
        arr = next((v for v in have["response"].values() if v.get("type") == "array"), {})
        have["product"] = (deref(spec, arr.get("items") or {}).get("properties") or {})
        given, names = (policy.get("api_fields") or {}).get(tool_name) or {}, {}
        for role, (where, keys) in roles.items():
            free = [n for n in have[where] if n != "customer_id" and n not in names.values()]
            names[role] = resolve(role, str(given.get(role) or ""), have[where], free, keys)
        out[tool_name] = names
    return out


def resolve(role, given, have, free, keys):
    """The policy's name when the file has it, else the role name, else the first free field with a word that starts with a keyword."""
    if given in have:
        return given
    if role in have or not have:
        return role
    return next((n for k in keys for n in free if any(w.startswith(k) for w in n.lower().split("_"))), role)
