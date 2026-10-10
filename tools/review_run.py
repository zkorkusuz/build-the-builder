"""Review loop: for every failed call of a run, show the decisions the agent made and who made each one.

    .venv/bin/python tools/review_run.py results/run4-reps3.json [--out results/review-run4.md]

For each failed call: what the ledger expected against what it got, the judge's reason, then the decision trail: every step
entered with the engine's reason, every tool call with the model's arguments and the result, and the lines said. Each decision
is tagged with its maker (code, hook, route, extraction, model) so that "which decision could code have made instead?" has an
answer. The engine's own reasons come from the call's system events (node_enter, route_evaluated, function_call_*).
"""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import freya

EXTRACTED = {"who", "confirm_failed_twice", "third_party_result", "identity_signal", "end_reason", "conversation_done"}
MODEL_FIELDS = {"product_id", "amount", "date", "field", "answer", "queue", "reason", "time", "text", "add_note_reason"}


def maker(reason):
    """Who decided a step change, from the engine's reason text."""
    r = str(reason or "")
    if r.startswith("Tool call:"):
        return "model (called the transition tool)"
    if r == "always always" or r == "always":
        return "code (passthrough)"
    if "max_node_turns" in r:
        return "turn cap"
    var = r.split("==")[0].strip().split(" ")[-1].strip("(") if "==" in r else ""
    if var in EXTRACTED:
        return "extraction (model judged the customer)"
    if var:
        return "route on " + var + " (set by hook or tool result)"
    return "engine: " + r[:60]


def trail(call_id):
    """The decision trail of one call."""
    lines, table = [], {}
    for m in freya.get_call(call_id).get("messages", []):
        role = m.get("role")
        if role in ("assistant", "user"):
            lines.append(("  " if role == "user" else "") + role.upper()[:5] + ": " + str(m.get("message"))[:200].replace("\n", " "))
            continue
        if role != "system":
            continue
        try:
            e = json.loads(m.get("message") or "{}")
        except ValueError:
            continue
        ev = e.get("event")
        if ev == "node_enter":
            lines.append("-> " + str(e.get("node")) + "  [" + maker(e.get("reason")) + "]")
        elif ev == "route_evaluated" and isinstance(e.get("variable_table"), dict):
            table = e["variable_table"]
        elif ev == "function_call_start" and e.get("function") != "code_exec":
            args = (e.get("args") or {}).get("body", e.get("args")) or {}
            chosen = {k: v for k, v in args.items() if k in MODEL_FIELDS} if isinstance(args, dict) else args
            who = "engine ran it from the variables" if e.get("function") in ("end_call", "close_call") else "model chose the arguments"
            lines.append("** " + str(e.get("function")) + " " + json.dumps(chosen)[:160] + "  [" + who + "]")
        elif ev == "function_call_complete" and e.get("function") != "code_exec":
            d = e.get("result", {}).get("data") if isinstance(e.get("result"), dict) else None
            if isinstance(d, dict):
                keep = {k: v for k, v in d.items() if k in ("ok", "error", "verified", "all_verified", "wrong_answers_left", "hint")}
                lines.append("   result " + json.dumps(keep) + ("  next: " + str(d.get("what_to_do_next"))[:120] if d.get("what_to_do_next") else "") + "  [hook wrote the instruction]")
        elif ev == "error":
            lines.append("!! " + json.dumps(e.get("message"))[:160])
    extracted = {k: (v.get("value") if isinstance(v, dict) else v) for k, v in table.items() if k in EXTRACTED or k in ("outcome", "reason", "id_state", "transfer_state", "promise_state", "promises_recorded", "notes_recorded", "promise_block")}
    return lines, extracted


def review(result_path, out_path):
    res = json.loads(pathlib.Path(result_path).read_text())
    reps = res.get("all_rows") or [res.get("rows", [])]
    out = ["# Review of " + str(result_path), "", "Agent " + str(res.get("agent_id")) + ", " + str(res.get("passed")) + " / " + str(res.get("total")) + " passed over " + str(len(reps)) + " run(s).", ""]
    flaky, failures = {}, 0
    for rep, rows in enumerate(reps, 1):
        for r in rows:
            if r.get("pass"):
                continue
            failures += 1
            flaky.setdefault(r["id"], []).append(rep)
            out += ["## " + r["id"] + " (run " + str(rep) + " of " + str(len(reps)) + ") " + str(r.get("family", "")), ""]
            for f in r.get("failed", []):
                kind = "JUDGE" if f.startswith("conversation:") else "LEDGER"
                out.append("- " + kind + ": " + f[:400])
            if not r.get("call_id"):
                out += ["", "(no call id)", ""]
                continue
            lines, extracted = trail(r["call_id"])
            out += ["", "Final variables: " + json.dumps(extracted)[:600], "", "```", *lines, "```", ""]
    out += ["## Consistency", ""]
    for cid, failed_in in sorted(flaky.items()):
        out.append("- " + cid + ": failed in run(s) " + ", ".join(map(str, failed_in)) + " of " + str(len(reps)) + (" (flaky: a model judgement to move into code, a hook or a route)" if 0 < len(failed_in) < len(reps) else " (always: a rule gap)"))
    out += ["", "## The question for each failure", "", "Which decision did the model make that code, a hook or a route could have made instead? Decisions tagged [model ...] and [extraction ...] above are the candidates; [hook ...] and [route ...] lines show where the deterministic parts already took over.", ""]
    text = "\n".join(out)
    pathlib.Path(out_path).write_text(text)
    print(text[:6000])
    print("\n... written to", out_path, "|", failures, "failed call(s)")


if __name__ == "__main__":
    args = sys.argv[1:]
    out = args[args.index("--out") + 1] if "--out" in args else str(ROOT / "results" / ("review-" + pathlib.Path(args[0]).stem + ".md"))
    review(args[0], out)
