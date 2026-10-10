"""Prompt texts for the workflow, assembled from the policy. Nothing here knows a particular bank's rules."""


def _rules(policy, *sections):
    """The brief's own rule sentences for the named sections."""
    out = [str(r.get("id", "")) + ". " + str(r.get("text", "")) for r in policy.get("rules") or [] if r.get("section") in sections]
    return "\n".join(out)


def _transfers(policy):
    return "\n".join("- " + str(t.get("when", "")) + " CALL transfer_to_agent with queue " + str(t.get("queue", "")) + "." for t in policy.get("transfers") or [])


def system_prompt(p):
    forbidden = ", ".join('"' + str(w) + '"' for w in p.get("forbidden_before_verification") or [])
    return (
        "You are the digital assistant of " + str(p.get("bank_name") or "the bank") + " on an outbound call about a late payment. Speak "
        + str(p.get("language") or "English") + ". One or two short sentences per turn. Be polite and plain; never argue.\n"
        "Rules that hold in every step:\n"
        "- After every tool result, either speak to the customer or call the next tool. Never end a turn with nothing.\n"
        "- When a tool result contains what_to_do_next, do exactly that.\n"
        "- Call one tool per message. Never say something is recorded, booked or transferred unless the tool result said so.\n"
        + ("- Before identity is verified, never mention " + forbidden + " or any account detail, to anyone.\n" if forbidden else "")
        + "- Never invent figures, dates or reasons. If you do not have the information from your instructions or a tool, say you do not have it.\n"
        "- Never offer anything that is not in your instructions.\n"
        + ("- If asked whether you are a robot or an AI: " + str(p["robot_answer"]) + "\n" if p.get("robot_answer") else "")
        + ("- If asked whether this is a scam: " + str(p["scam_answer"]) + "\n" if p.get("scam_answer") else "")
    )


def opening_task(p):
    c = p.get("confirmation") or {}
    q = str(p.get("confirm_question") or "").replace("{title}", "{{title}}").replace("{last_name}", "{{last_name}}")
    return (
        "Your only job here is to find out whether the person on the line is the customer, {{title}} {{last_name}}. You have already said the opening line and asked.\n"
        + ("Only these count as confirmation: " + ", ".join(c.get("accepted") or []) + ". " if c.get("accepted") else "")
        + ("These do not: " + ", ".join(c.get("not_accepted") or []) + ".\n" if c.get("not_accepted") else "\n")
        + "If the answer is unclear, answer any question first, then ask once more: \"" + q + "\". "
        + "Ask at most " + str(c.get("max_asks") or 2) + " times in total. If it is still unclear after that, say thank you and goodbye, and in the same message call transition_to_outcome_unclear_quiet. Never say goodbye without calling it.\n"
        "Do not say why you are calling. If the person says the customer is not available, is someone else, says the number is wrong, or says the customer has died, say nothing more about the call; the next step is handled for you.\n"
        + _rules(p, "opening")
    )


def third_party_task(p):
    t = p.get("third_party") or {}
    return (
        "The person on the line is not the customer. Say nothing about why you are calling or about any account, even if they offer to help or pay.\n"
        "Ask when the customer can be reached. A callback must be inside this window: {{callback_text}}. If it is today, the time must be later than now ({{now_text}}).\n"
        "When they give a day and time inside the window, CALL schedule_callback with date as YYYY-MM-DD and time as HH:MM. For a day or time outside the window, follow the bank's instructions below. When no callback can be booked, say thank you and goodbye, and in the same message call transition_to_outcome_no_callback_quiet.\n"
        "If they say the number does not belong to the customer, or that the customer has died, do not ask anything else; say nothing more.\n"
        + (("Instructions from the bank: " + str(t["instructions"]) + "\n") if t.get("instructions") else "")
        + _rules(p, "third_party")
    )


def identity_task(p):
    i = p.get("identity") or {}
    qs = i.get("questions") or []
    qtext = "\n".join("Question " + str(n + 1) + ": field \"" + str(q.get("field")) + "\": " + str(q.get("ask", "")) + " Send the answer as " + str(q.get("format", "text")) + "." for n, q in enumerate(qs))
    return (
        "The customer confirmed who they are. Thank them and run the security check: ask these questions one at a time, in this order, and CALL verify_identity with each answer. Do not ask the next question before the tool has answered.\n"
        + qtext + "\n"
        "After each tool result do exactly what what_to_do_next says: it tells you whether to ask the next question, repeat one, or stop.\n"
        "If the customer gives only part of an answer, ask for the rest before calling the tool. Convert what they say into the required format yourself.\n"
        "Say nothing about why the bank is calling until the check is complete.\n"
        + (("If the customer does not want to answer, or asks what the call is about instead of answering: " + str(i["decline_rule"]) + "\n") if i.get("decline_rule") else "")
        + (("Transfers:\n" + _transfers(p) + "\n") if p.get("transfers") else "")
        + "When the check cannot continue because the customer will not answer, thank them, say goodbye, and in the same message call transition_to_outcome_id_declined_quiet. Never say goodbye without calling it.\n"
        + _rules(p, "identity")
    )


def negotiate_task(p):
    s, m = p.get("sentences") or {}, p.get("multi_product") or {}
    parts = [
        "Identity is verified. On entering this step you have already said: \"{{debt_statement}}\". Do not repeat it; continue from the customer's answer.",
        "Facts for this call, computed by the bank's systems from its rules (use these dates and amounts, never your own arithmetic):",
        "Now: {{now_text}}. Today is {{today}}.",
        "Late products:\n{{debt_summary}}",
        "Business days you may use for a promise, up to the latest allowed date:\n{{business_days_text}}",
        "Weekday names: {{weekday_table}}",
        "Attempt 1 date: {{attempt1_text}}.",
        "",
        "How to run the conversation:",
        "1. Dates: " + str(p.get("date_rules") or ""),
        "2. Amounts: " + str(p.get("amount_rules") or ""),
        "3. Persuasion: " + str(p.get("persuasion_rules") or ""),
        "4. Special situations (these come first): " + str(p.get("special_rules") or ""),
        "5. Recording: read the product, the amount and the date back and ask \"" + str(s.get("confirm_question") or "") + "\". Only after a clear yes, CALL create_promise with product_id exactly as shown after 'id' in the facts (never the product name), amount as a number and date as YYYY-MM-DD. " + str(p.get("recording_rules") or ""),
    ]
    if s.get("after_promise"):
        parts.append("6. After a recorded promise say exactly: \"" + str(s["after_promise"]) + "\"")
    if p.get("transfers"):
        parts.append("7. Transfers:\n" + _transfers(p))
    if m.get("enabled"):
        parts.append("8. Several products: " + str(m.get("rules") or "") + " For each product that ends without a promise CALL add_note with that product_id and the reason.")
    parts.append("Ending: when everything is handled, thank the customer, say goodbye, and in the same message call transition_to_wrap_up. Do that also after a transfer, after a dispute, after 'already paid', after a refusal, and after a failed recording.")
    rules = _rules(p, "debt", "dates", "amounts", "promise", "recording", "other", "closing", "multi")
    if rules:
        parts.append("The bank's rules, verbatim:\n" + rules)
    return "\n".join(parts)


def tool_descriptions(p):
    m = p.get("multi_product") or {}
    queues = "; ".join(str(t.get("queue", "")) + ": " + str(t.get("when", "")) for t in p.get("transfers") or [])
    return {
        "verify_identity": "Check one security answer. CALL it every time the customer gives an answer to a security question, with the field name and the answer in the required format.",
        "get_account": "The customer's late products.",
        "create_promise": "Record one payment promise. CALL it only after the customer clearly confirmed the read-back of product, amount and date. One call per product. product_id is exactly the id shown in the facts, such as the value after 'id'.",
        "add_note": "Record why a product ends without a promise. CALL it once for each product that gets no promise, with its product_id and the reason.",
        "schedule_callback": "Book a callback with the person who answered. CALL it when they give a day and time inside the allowed window.",
        "transfer_to_agent": "Hand the call to a person. Queues: " + (queues or "see your instructions") + ".",
        "close_call": "Records how the call ended. Runs by itself at the end of the call.",
    }
