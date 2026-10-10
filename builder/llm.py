"""One way to ask the builder model a question. Runs Claude through the Agent SDK in an isolated folder with no tools."""
import asyncio, json, os, re, time

MODEL = os.environ.get("BUILDER_MODEL", "claude-opus-5-5")


def ask(prompt, workdir, trace, purpose, system=None):
    """Return the model's text answer. Logs model, purpose, duration and cost to the trace."""
    from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, query

    async def run():
        options = ClaudeAgentOptions(cwd=str(workdir), model=MODEL, allowed_tools=[], permission_mode="dontAsk", max_turns=2, setting_sources=[],
                                     system_prompt=system or "You answer with the requested JSON only, no commentary.")
        text, cost = "", 0.0
        async for m in query(prompt=prompt, options=options):
            if isinstance(m, AssistantMessage):
                text += "".join(b.text for b in m.content if isinstance(b, TextBlock))
            elif isinstance(m, ResultMessage):
                cost = m.total_cost_usd or 0.0
        return text, cost

    t0 = time.time()
    text, cost = asyncio.run(run())
    trace("model call: " + MODEL + " | " + purpose + " | " + str(round(time.time() - t0)) + " s | $" + str(round(cost, 3)) + " | " + str(len(text)) + " chars")
    return text


def parse_json(text):
    """The JSON object in a model answer: a ```json fence, or the outermost braces."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    raw = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    return json.loads(raw)
