"""Design: the builder model writes the whole workflow from the documents and the tool API, for a case the practice template does not fit.

The platform reference (docs/workflow-format.md and docs/tools-and-code.md) goes into the prompt verbatim so the model follows the
platform's own rules; the kit's lint and the platform's dry run check the result, and a repair pass fixes what they flag.
"""
import json
import pathlib

from builder import lint, normalize

ROOT = pathlib.Path(__file__).resolve().parent.parent
REFERENCE_DOCS = ("workflow-format.md", "tools-and-code.md")
DESIGN_TIMEOUT_S, REPAIR_TIMEOUT_S = 20 * 60, 6 * 60     # a whole workflow is a long answer; the build budget still caps both

FIT_QUESTION = """Below are a bank's documents for a phone agent. Answer with one JSON object {"outbound_collections": true or false, "summary": "<one sentence in English: what the agent does>"} in a ```json fence and nothing else.
outbound_collections is true only when the agent makes an OUTBOUND call about a late payment, asks the customer security questions to verify them, and records payment promises with their dates and amounts. Any other kind of call (an inbound inquiry, a service request, an information line) is false."""

DESIGN = """You are building the complete workflow JSON of a phone agent on the Freya platform for the bank described in the documents below.
Answer with one JSON object in a ```json fence and nothing else: the workflow, the value of "workflow" in the platform's request body.

Work like this:
1. Read every document completely. Later documents (mails, corrections, memos) override earlier ones when they conflict; where documents disagree, follow the most recent binding source and keep the agent consistent with the example conversations.
2. Design the call as a graph of nodes exactly as the platform reference describes: conversation nodes for dialogue, api_request or code nodes for calls the engine runs on entry, end_call nodes for every way the call ends. Every path reaches an end_call node. Each conversation node's task_message is a complete instruction for that step, written in English; every sentence the agent must say to the caller is in the documents' language, quoted verbatim where the documents give it.
3. Tools: every service the agent uses is a tool with handler __function__:api_call whose url is the tool API's servers url plus the documented path, with the documented method, headers and request fields (each body field a leaf under body.properties with its own default, type, description and enum). A field whose value comes from a call variable or an earlier result is baked with a "{{variable}}" default; a field the model must fill has a default "{{<field name>}}" that nothing sets. Read every result through response_mapping (paths start with data.) and route on the mapped variables or the flattened <tool>_response.data.<field> keys. Give every api_call tool a post_process_code hook, written as the reference shows, that pops the header and adds a plain-English what_to_do_next line inside result["data"] for every outcome the service documents (each success shape and each error status), so the agent knows what to say or do next; hooks never raise (try, except Exception: pass).
4. Call variables: use exactly the variables the documents say every call provides, with those names, and put example values for them in test_variables. Never ask the caller for something the documents say the agent already has. Every date or time decision uses the call's own time variable, never the system clock; compute dates in a code node (json, re and datetime only, no double braces, never raises) and give the model finished facts as text through variables.
5. Prompts: one or two short sentences per turn in the caller's language; say every number, amount, date and time in words in that language; call one tool per message and speak after every tool result; never say an action was done unless the tool result says so; never invent amounts, dates or facts; do only what the documents allow and hand over to a person exactly as the documents say. Rules that hold in every step go in system_prompt.
6. Routing: deterministic conditions before matches_intent; fork on an extracted enum (min_confidence on every extraction) rather than on several competing intents; every passthrough node ends with an always transition; every node with max_node_turns has a max_turn_transition; no null anywhere; no const; tools only on conversation nodes; pre_actions only on api_request and code nodes; each node's name equals its key; leave agent_config out.
7. Make sure the workflow handles every example conversation in the documents and every kind of scenario they mention (ordinary, edge, adversarial) as the documents require, but do not write that check out: answer with the workflow only.
8. Size limits, which matter because a long answer runs out of time: at most 14 nodes; each task_message at most 180 words (put rules that hold everywhere in system_prompt once, never repeated per node; a fixed sentence goes in on_enter as tts text, not in a prompt); each hook at most 10 short lines; transition and tool descriptions one sentence; no comments or prose outside the fence; the JSON compact, with no indentation and no line breaks between keys (line breaks only inside code strings)."""

REPAIR = """The workflow below was rejected. Fix every problem listed, keep everything else exactly as it is, and answer with the complete corrected workflow JSON in a ```json fence and nothing else.

Problems:
"""


def reference():
    return "\n\n".join("=== PLATFORM REFERENCE: " + n + " ===\n" + (ROOT / "docs" / n).read_text() for n in REFERENCE_DOCS)


def fits_template(texts, workdir, trace, ask, parse_json):
    """True when the documents describe the outbound collections call the practice template was built for."""
    try:
        answer = parse_json(ask(FIT_QUESTION + "\n\n" + normalize.documents_text(texts), workdir, trace, "plan: does the practice template fit the documents"))
        fit = str(answer.get("outbound_collections")).lower() == "true"
        trace("plan: " + ("the practice template fits" if fit else "the practice template does not fit, the model designs the workflow") + ": " + " ".join(str(answer.get("summary") or "").split())[:240])
        return fit
    except Exception as e:
        trace("plan: could not classify the documents (" + str(e)[:120] + "); using the practice template")
        return True


def design(texts, spec, workdir, trace, ask, parse_json):
    """The model's workflow for the documents, tidied and linted. Returns (workflow, problems)."""
    prompt = (DESIGN + "\n\n" + reference() + "\n\n" + normalize.documents_text(texts)
              + "\n\n=== TOOL API (OpenAPI of the bank's services; its servers url is the mock the tools call) ===\n" + json.dumps(spec, indent=1, ensure_ascii=False))
    workflow = tidy(parse_json(ask(prompt, workdir, trace, "design: the whole workflow from the documents and the tool API", timeout=DESIGN_TIMEOUT_S, max_turns=8)))
    problems = lint.check(workflow)
    trace("design: " + str(len(workflow.get("nodes") or {})) + " steps, lint " + (" | ".join(problems) or "clean"))
    return workflow, problems


def repair(workflow, problems, workdir, trace, ask, parse_json):
    """One model pass over the listed problems (lint findings or the platform's rejection). Returns (workflow, remaining problems)."""
    prompt = (REPAIR + "\n".join("- " + str(p) for p in problems) + "\n\n" + reference()
              + "\n\n=== WORKFLOW ===\n```json\n" + json.dumps(workflow, indent=1, ensure_ascii=False) + "\n```")
    fixed = tidy(parse_json(ask(prompt, workdir, trace, "design: repair of " + str(len(problems)) + " problem(s)", timeout=REPAIR_TIMEOUT_S, max_turns=8)))
    remaining = lint.check(fixed)
    trace("design: repaired, " + str(len(fixed.get("nodes") or {})) + " steps, lint " + (" | ".join(remaining) or "clean"))
    return fixed, remaining


def tidy(workflow):
    """Mechanical fixes for what the platform punishes silently: node names, misplaced tools, agent_config, nulls."""
    workflow = strip_null(workflow)
    workflow.pop("agent_config", None)
    for key, node in (workflow.get("nodes") or {}).items():
        if isinstance(node, dict):
            node["name"] = key
            if node.get("node_type") == "conversation":
                node.pop("pre_actions", None)
            if node.get("node_type") in ("api_request", "code"):
                node.pop("tools", None)
            if node.get("node_type") == "end_call":
                node["transitions"] = []
    return workflow


def strip_null(value):
    if isinstance(value, dict):
        return {k: strip_null(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [strip_null(v) for v in value if v is not None]
    return value
