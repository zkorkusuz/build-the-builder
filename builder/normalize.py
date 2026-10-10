"""Normalize: the brief file(s) and the tool API file become one policy.json in a fixed schema."""
import json, pathlib

SCHEMA = (pathlib.Path(__file__).parent / "policy_schema.json").read_text()
REQUIRED = ["opening_sentence", "confirm_question", "identity", "calendar", "bands", "outcomes", "sentences", "product_words", "floor_field", "end_reasons"]
SITUATIONS = ["unclear", "callback", "no_callback", "wrong_number", "deceased", "id_failed", "id_declined", "promise"]

INSTRUCTIONS = """You are turning a bank's instructions for an outbound late-payment phone call into one JSON policy file.
Read every brief document below completely, sentence by sentence. Later documents (memos, corrections) override earlier ones when they conflict.
Fill every field of the schema from the briefs and the tool API file. Take tool field names, enum values, outcome names, reasons and queue names from the tool API file. Never invent a value: if the briefs do not give one, use an empty string, and for lists an empty list.
Rules text fields (date_rules, amount_rules, persuasion_rules, special_rules, recording_rules, third_party.instructions, identity.decline_rule, multi_product.rules) must contain every rule of that kind, rewritten as instructions to the phone agent, complete and in the brief's own words where possible. Use the phrase "latest allowed date" for the per-product deadline and "floor" for the minimum amount; the agent receives the computed dates and amounts.
The outcomes map: each situation key is a moment the call ends before or without a payment conversation; fill the outcome and reason values the brief's closing table prescribes for it. end_reasons lists every way a verified call can end without a promise, with its outcome and reason from the table and the add_note reason value for it, if the brief uses notes. transfers lists every queue of the tool API with the situation that leads to it. no_reason_outcomes lists the outcome values the table shows with no reason. attempt1_rule encodes which date the first persuasion attempt proposes.
rules: list every rule in the briefs, verbatim, one entry per rule sentence, with its section. Keep the brief's own numbers or letters as ids; when a document has no numbering (an email, a memo), number the rules yourself in reading order (E1, E2, ... for the first document, M1, M2, ... for a memo). A memo correction becomes its own rule entry too.
Answer with one JSON object in a ```json fence and nothing else. Integers must be JSON numbers, booleans JSON booleans."""


def prompt(briefs, spec_text):
    docs = "\n\n".join("=== BRIEF DOCUMENT " + str(i + 1) + ": " + name + " ===\n" + text for i, (name, text) in enumerate(briefs))
    return INSTRUCTIONS + "\n\n=== SCHEMA (fill every field; <...> describes what goes there) ===\n" + SCHEMA + "\n\n" + docs + "\n\n=== TOOL API FILE ===\n" + spec_text


def problems(policy):
    """What is missing or malformed in a policy. Empty means usable."""
    out = []
    for k in REQUIRED:
        if not policy.get(k):
            out.append("missing " + k)
    for s in SITUATIONS:
        if not (policy.get("outcomes", {}).get(s) or {}).get("outcome"):
            out.append("outcome for " + s + " missing")
    if not policy.get("identity", {}).get("questions"):
        out.append("identity.questions empty")
    for e in policy.get("end_reasons") or []:
        if not e.get("key") or not e.get("outcome"):
            out.append("end_reason without key or outcome: " + json.dumps(e)[:80])
    for t in policy.get("transfers") or []:
        if not t.get("queue") or not t.get("outcome"):
            out.append("transfer without queue or outcome: " + json.dumps(t)[:80])
    rule = policy.get("attempt1_rule")
    if not isinstance(rule, dict) or str(rule.get("rule")) not in ("last_business_day_of_week", "next_business_day", "nth_business_day", "deadline", "none"):
        out.append("attempt1_rule.rule must be one of last_business_day_of_week, next_business_day, nth_business_day, deadline, none")
    for b in policy.get("bands", []):
        for k in ("days_late_min", "days_late_max", "deadline_business_days", "attempts"):
            try:
                b[k] = int(b[k])
            except (KeyError, TypeError, ValueError):
                out.append("band " + str(b.get("name")) + " has no integer " + k)
    if not policy.get("calendar", {}).get("business_weekdays"):
        policy.setdefault("calendar", {})["business_weekdays"] = [0, 1, 2, 3, 4]
    mp = policy.get("multi_product")
    if isinstance(mp, dict) and not isinstance(mp.get("enabled"), bool):
        mp["enabled"] = str(mp.get("enabled")).lower() == "true"
    return out


def normalize(briefs, spec_text, workdir, trace, ask, parse_json):
    """One model call, one repair call at most. Returns the policy or raises."""
    text = ask(prompt(briefs, spec_text), workdir, trace, "normalize: briefs and tool API into policy.json")
    policy = parse_json(text)
    missing = problems(policy)
    if missing:
        trace("normalize: repairing " + "; ".join(missing))
        fix = ask("This policy JSON has problems: " + "; ".join(missing) + ".\nReturn the complete corrected JSON object in a ```json fence, filling the missing values from the brief documents and tool API file below.\n\n```json\n"
                  + json.dumps(policy, indent=1) + "\n```\n\n" + prompt(briefs, spec_text), workdir, trace, "normalize: repair missing fields")
        policy = parse_json(fix)
        missing = problems(policy)
        if missing:
            raise RuntimeError("policy still incomplete: " + "; ".join(missing))
    return policy
