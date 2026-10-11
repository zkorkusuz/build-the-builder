"""Local checks for a rendered workflow: every platform gotcha that fails silently on Freya. Returns a list of problems."""
import re

PLACEHOLDER = re.compile(r"\{\{([a-zA-Z_][\w.]*)\}\}")
CALL_VARS = {"customer_id", "first_name", "last_name", "title", "now"}


def walk(obj, path=""):
    yield path, obj
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, path + "/" + str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, path + "[" + str(i) + "]")


def set_variables(wf):
    """Names the workflow can set: mappings, code assignments, extraction, result keys."""
    names = set(CALL_VARS)
    for path, obj in walk(wf):
        if isinstance(obj, dict):
            if "variable" in obj and "path" in obj:
                names.add(obj["variable"])
            if obj.get("name") and path.endswith("]") and "extraction_schema" in path:
                names.add(obj["name"])
            if "code" in obj and isinstance(obj.get("code"), dict) and "default" in obj["code"]:
                names |= set(re.findall(r"vars\['([\w.]+)'\]\s*=", obj["code"]["default"]))
                names |= set(re.findall(r"\('(\w+)',\s*'[^']*'\)", obj["code"]["default"]))
                if "calendar_facts" in obj["code"]["default"]:
                    from builder import dates
                    names |= set(dates.calendar_facts("2000-01-03T09:00", {}).keys())
    return names


def check(wf):
    problems, nodes = [], wf.get("nodes", {})
    for path, obj in walk(wf):
        if obj is None:
            problems.append("null at " + path)
        if isinstance(obj, dict) and "const" in obj:
            problems.append("const used at " + path)
    if wf.get("initial_node") not in nodes:
        problems.append("initial_node missing")
    for key, n in nodes.items():
        kind = n.get("node_type")
        if n.get("name") != key:
            problems.append(key + ": name differs from key")
        if kind == "conversation" and n.get("pre_actions"):
            problems.append(key + ": pre_actions on a conversation node are dropped")
        if kind in ("api_request", "code") and n.get("tools"):
            problems.append(key + ": tools on a " + kind + " node are dropped")
        if n.get("passthrough"):
            trs = n.get("transitions", [])
            if not trs or trs[-1].get("condition", {}).get("operator") != "always":
                problems.append(key + ": passthrough node without a final always transition")
            if n.get("passthrough_default_transition") not in nodes:
                problems.append(key + ": passthrough_default_transition missing")
        if n.get("max_node_turns") and n.get("max_turn_transition") not in nodes:
            problems.append(key + ": max_node_turns without a valid max_turn_transition")
        if kind == "end_call" and not n.get("terminal"):
            problems.append(key + ": end_call node without terminal")
        for t in n.get("transitions", []):
            if t.get("target_node") not in nodes:
                problems.append(key + ": transition to unknown node " + str(t.get("target_node")))
        for e in n.get("extraction_schema", []):
            if "min_confidence" not in e:
                problems.append(key + ": extraction " + str(e.get("name")) + " without min_confidence")
        for path, obj in walk(n):
            if isinstance(obj, dict) and obj.get("handler") == "__function__:code_exec":
                code = obj["parameters"]["properties"]["code"]["default"]
                if "{{" in code or "}}" in code:
                    problems.append(key + ": code contains double braces")
                try:
                    compile(code, key, "exec")
                except SyntaxError as e:
                    problems.append(key + ": code does not compile: " + str(e))
            if isinstance(obj, dict) and "path" in obj and "variable" in obj and not str(obj["path"]).startswith("data."):
                problems.append(key + ": response_mapping path without data. prefix: " + str(obj["path"]))
            for hook in ("pre_process_code", "post_process_code"):
                if isinstance(obj, dict) and obj.get(hook):
                    try:
                        compile(obj[hook], key + hook, "exec")
                    except SyntaxError as e:
                        problems.append(key + ": " + hook + " does not compile: " + str(e))
    for path, obj in walk(wf.get("tools", [])):
        if isinstance(obj, dict) and obj.get("function", {}).get("handler") == "__function__:api_call" and not obj.get("config", {}).get("alwaysRunsAt"):
            problems.append("workflow-level tool without alwaysRunsAt never runs: " + path)
    closers = [k for k, n in nodes.items() if any(t.get("function", {}).get("name") == "close_call" for t in n.get("pre_actions", []))]
    for key, n in nodes.items():
        if n.get("node_type") == "end_call" and closers and not any(t.get("target_node") == key for c in closers for t in nodes[c].get("transitions", [])):
            problems.append(key + ": an end node reachable without a close_call step before it")
    known = set_variables(wf)
    for key, n in nodes.items():
        texts = [n.get("task_message", ""), n.get("on_enter", {}).get("text", "")]
        for text in texts:
            for var in PLACEHOLDER.findall(text or ""):
                if var not in known:
                    problems.append(key + ": prompt references {{" + var + "}} which nothing sets")
    return problems
