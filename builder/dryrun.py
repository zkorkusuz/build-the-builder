"""Data-path dry run of a designed workflow: follow the engine-run steps from the initial node with the workflow's test variables,
calling the live mock for api nodes, running pre-hooks, post-hooks, mappings and code steps, and taking deterministic transitions.

A hook that reads the bank's answer at the wrong depth, or a request whose field the engine dropped, shows up here as a non-200
answer or a call that ends before any conversation step, with the exact trail to hand to the model for a repair.
"""
import datetime
import json
import re
import urllib.request

MAX_STEPS = 12


def walk(workflow, trace=lambda line: None):
    """Returns (problems, trail): problems is a list of sentences, trail the step-by-step account."""
    nodes, variables = workflow.get("nodes") or {}, {k: str(v) for k, v in (workflow.get("test_variables") or {}).items()}
    key, trail, problems, seen_conversation = workflow.get("initial_node"), [], [], False
    for _ in range(MAX_STEPS):
        node = nodes.get(key)
        if node is None:
            problems.append("the path reaches an unknown node " + str(key)); break
        kind = node.get("node_type")
        if kind == "conversation":
            trail.append(key + ": conversation step reached"); seen_conversation = True; break
        if kind == "end_call":
            trail.append(key + ": the call ends here")
            if not seen_conversation:
                problems.append("the call ends at " + key + " before any conversation step")
            break
        if kind in ("api_request", "code"):
            for tool in node.get("pre_actions") or []:
                trail.append(run_action(key, node, tool, variables, problems))
        key = next_node(node, variables, trail)
    return problems, trail


def run_action(key, node, tool, variables, problems):
    fn = tool.get("function") or {}
    props = (fn.get("parameters") or {}).get("properties") or {}
    if fn.get("handler") == "__function__:code_exec":
        before = set(variables)
        exec_quiet(props.get("code", {}).get("default", ""), {"vars": variables})
        return key + ": code set " + ", ".join(k + "=" + short(variables[k]) for k in sorted(set(variables) - before))[:400]
    if fn.get("handler") != "__function__:api_call":
        return key + ": " + str(fn.get("handler")) + " skipped"
    config = {"url": fill(props.get("url", {}).get("default", ""), variables), "method": props.get("method", {}).get("default", "POST"),
              "headers": {}, "body": bake(props.get("body") or {}, variables)}
    exec_quiet(tool.get("pre_process_code") or "", {"vars": variables, "config": config})
    status, body = http(config["method"], config["url"], config["body"])
    result = {"status": "success" if status < 300 else "error", "data": body, "status_code": status, "header": {}}
    if status < 300:                                   # the platform skips the post-hook on an error answer
        exec_quiet(tool.get("post_process_code") or "", {"vars": variables, "result": result})
    for m in (node.get("response_mapping") or []) + (tool.get("response_mapping") or []):
        variables[m["variable"]] = dig(result, m.get("path", ""))
    name = fn.get("name") or key
    for prefix in {key, name}:
        variables[prefix + "_status_code"] = str(status); variables[prefix + "_success_count"] = str(int(status < 300)); variables[prefix + "_failure_count"] = str(int(status >= 300))
        flatten(prefix + "_response", result, variables)
    if status >= 300:
        problems.append(key + " got HTTP " + str(status) + " for the request " + json.dumps(config["body"], ensure_ascii=False)[:200])
    mapped = ", ".join(m["variable"] + "=" + short(variables.get(m["variable"])) for m in (node.get("response_mapping") or []))
    return key + ": " + config["method"] + " " + config["url"].rsplit("/", 1)[-1] + " " + json.dumps(config["body"], ensure_ascii=False)[:160] + " -> " + str(status) + " " + json.dumps(body, ensure_ascii=False)[:220] + (" | mapped " + mapped if mapped else "")


def bake(schema, variables):
    """A request body from its schema: literal defaults kept, {{var}} defaults filled or dropped when empty, as the engine does."""
    out = {}
    for name, prop in (schema.get("properties") or {}).items():
        if not isinstance(prop, dict):
            continue
        if prop.get("type") == "object" or "properties" in prop:
            inner = bake(prop, variables)
            if inner:
                out[name] = inner
        elif "default" in prop:
            value = fill(prop["default"], variables) if isinstance(prop["default"], str) else prop["default"]
            if value not in (None, ""):
                out[name] = value
    return out


def fill(text, variables):
    def one(m):
        return str(variables.get(m.group(1), ""))
    return re.sub(r"\{\{\s*([\w.]+)(?::json)?\s*\}\}", one, str(text))


def http(method, url, body):
    try:
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method=method, headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0 build-the-builder"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8") or "null")
        except Exception:
            return e.code, None
    except Exception as e:
        return 599, {"error": str(e)[:120]}


def dig(obj, path):
    for part in path.split("."):
        obj = obj.get(part) if isinstance(obj, dict) else None
    return obj if isinstance(obj, (str, int, float)) or obj is None else json.dumps(obj, ensure_ascii=False)


def flatten(prefix, value, variables, depth=0):
    if isinstance(value, dict) and depth < 4:
        for k, v in value.items():
            flatten(prefix + "." + str(k), v, variables, depth + 1)
    elif not isinstance(value, (dict, list)):
        variables[prefix] = str(value) if value is not None else ""


def exec_quiet(code, names):
    try:
        exec(code, {"json": json, "re": re, "datetime": datetime, **names})
    except Exception:
        pass


def next_node(node, variables, trail):
    for t in node.get("transitions") or []:
        if holds(t.get("condition") or {}, variables):
            trail.append("  -> " + str(t.get("target_node")) + " (" + str(t.get("description") or "")[:60] + ")")
            return t.get("target_node")
    trail.append("  -> " + str(node.get("passthrough_default_transition")) + " (default)")
    return node.get("passthrough_default_transition")


def holds(cond, variables):
    if "conditions" in cond:
        parts = [holds(c, variables) for c in cond.get("conditions") or []]
        return all(parts) if str(cond.get("logic", "or")).lower() == "and" else any(parts)
    op, var, operand = cond.get("operator"), str(variables.get(cond.get("variable", ""), "")), str(cond.get("operand", ""))
    if op == "always": return True
    if op == "equals": return var == operand
    if op == "not_equals": return var != operand
    if op == "is_set": return var != ""
    if op == "is_not_set": return var == ""
    if op == "contains": return operand.lower() in var.lower()
    try:
        if op == "greater_than": return float(var) > float(operand)
        if op == "less_than": return float(var) < float(operand)
    except ValueError:
        return False
    return False


def short(v):
    s = str(v) if v is not None else ""
    return s[:60] + ("..." if len(s) > 60 else "")
