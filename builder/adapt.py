"""Adapt: one model pass that checks every rule of the brief against the rendered prompts and adds what is missing."""
import json

NODES = ["opening", "third_party", "identity", "negotiate"]
INSTRUCTIONS = """Below are the four conversation steps of a phone agent (their instructions) and the complete list of the bank's rules.
The agent's call flow, dates, amounts and tool handling are fixed by code; you only improve the instruction text.
For each rule, check whether the step where it applies already covers it. Return additions for rules that are missing or stated too weakly, as a JSON object
{"opening": "...", "third_party": "...", "identity": "...", "negotiate": "..."} where each value is text to append to that step's instructions (empty string when nothing is missing).
Write short imperative sentences. Quote any sentence the rules require verbatim. Do not repeat what is already there. Do not describe steps or routing. Answer with the JSON object in a ```json fence only."""


def adapt(workflow, policy, workdir, trace, ask, parse_json):
    """Append model-written additions to the task messages. Never removes anything."""
    steps = "\n\n".join("=== STEP " + n + " ===\n" + workflow["nodes"][n]["task_message"] for n in NODES)
    rules = "\n".join(str(r.get("id", "")) + " [" + str(r.get("section", "")) + "] " + str(r.get("text", "")) for r in policy.get("rules", []))
    if not rules.strip():
        trace("adapt: skipped, the policy lists no rules")
        return workflow
    text = ask(INSTRUCTIONS + "\n\n" + steps + "\n\n=== RULES ===\n" + rules, workdir, trace, "adapt: rule-by-rule check of the prompts")
    additions = parse_json(text)
    for n in NODES:
        extra = str(additions.get(n) or "").strip()
        if extra:
            workflow["nodes"][n]["task_message"] += "\n\nAlso:\n" + extra
            trace("adapt: added to " + n + ": " + " ".join(extra.split()))
    return workflow
