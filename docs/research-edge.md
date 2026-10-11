# Research edge: what 2024 to 2026 work on agent reliability says we should do next

Written 11 October 2026 for the Build the Builder team, from a read of 18 papers and reports (10 in full, 8 as
supporting notes). The question asked of every source: what could the builder do in the next 10 hours that raises
pass^3 on 60 hidden customers scored by a ledger check and an LLM judge?

How to read it. Each full entry has a summary, a line on whether the finding transfers to a fixed-model Freya
workflow agent, and one to three actions with an impact and effort estimate. Section 3 lists where the literature
qualifies the team's design principle ("move the decision from the model into code"). Section 4 is the ranked top
five. Numbers are quoted from the papers; where a paper's method is training-based and does not transfer, the entry
says so and keeps only the measurement.

The team's four residual failure classes are referred to as (a) the model reformatting or joining partial answers,
(b) one clarifying question too many, (c) a literal or inconsistent judge, (d) platform flakiness. Nothing below
helps with (d).

## 1. Full entries

### 1.1 The Lost-in-Conversation thread: two papers

**LLMs Get Lost in Multi-Turn Conversation.** Laban, Hayashi, Zhou, Neville. arXiv 2505.06120, May 2025, ICLR 2026.
https://arxiv.org/abs/2505.06120

**Intent Mismatch Causes LLMs to Get Lost in Multi-Turn Conversation.** Liu, Zhu, Feng, Ma, Wang, Meng. arXiv
2602.07338, February 2026. https://arxiv.org/abs/2602.07338

Summary. Laban et al. ran 200,000 simulated conversations over 15 models and six tasks. When a fully specified
instruction is revealed one piece per turn instead of all at once, average performance drops 39 percent (roughly 90
to 65). The drop is mostly unreliability, not ability: the best-case score falls 16 percent while the spread between
runs rises 112 percent. Four causes: premature answers, over-verbosity (the model's own long turns introduce
assumptions), locking in on an early wrong assumption, and leaning on earlier attempts; middle turns get the least
weight. Temperature 0 cut unreliability 50 to 80 percent in single-turn settings but only 15 to 20 percent for
GPT-4o in multi-turn and nothing for GPT-4o-mini; with both sides at temperature 0, unreliability stayed near 30
percent. A "snowball" control that restates every fact given so far on each turn recovered 15 to 20 percent of the
loss. Liu et al. argue the cause is an intent gap, not capability: the degradation is about 60 percent relative at
every model scale (GPT-5.2 scores 92.7 fully specified vs 48.5 sharded). Their training-free "Mediator" rewrites the
user's latest input into a fully specified instruction before the assistant answers: GPT-4o-mini 53.6 to 73.9,
GPT-5.2 48.5 to 72.6, reliability 54.2 to 68.8. A naive running summary (+1.1) and RAG memory (+2.9) barely help.

Transfers? Yes, directly. This is the mechanism behind pass^3 loss on a fixed model, and the Mediator is a
pre-processing step that Freya's extraction plus a code step can play.

Actions.
1. Make the extraction step the mediator. Extract structured fields from each customer turn, merge them in code,
   and hand the next node a one-line imperative restatement of the consolidated state ("Known: 150, 14 March, year
   not given. Ask only for the year." or "Customer promised 150 on 14 March 2027 for the card. Read it back in
   one sentence, then call record_promise."). The model should never be the thing that joins "14", "March" and
   "next year". Impact high for failure (a). Effort medium; the plumbing exists, the change is what flows through
   what_to_do_next or a templated prompt var.
2. Make dialogue nodes short-answer by construction: one question per turn, at most two sentences, do not
   paraphrase what the customer said. Over-verbosity is one of the four causes and also feeds judge distraction
   (entry 1.9). Impact medium, effort small.
3. Do not spend time on temperature or sampling even if the platform exposes it; the paper shows it does not fix
   multi-turn unreliability. Impact low, effort none.

### 1.2 ToolSandbox

Lu et al. (Apple). arXiv 2408.04682, August 2024. https://arxiv.org/abs/2408.04682

Summary. A stateful conversational tool-use benchmark with 1,032 scenarios scored by milestones (required events)
and minefields (events that must never happen; one hit scores the whole trajectory 0). "Canonicalization", turning
what the user said into the form the API expects ("this Friday" into a date, "1B" into a number, a landmark into
coordinates), is "a challenging category for all models": GPT-4o 76.6, Claude 3 Opus 71.1, Gemini 1.5 Pro 51.6 out
of 100. Observed failure modes: hallucinated timestamps instead of deriving them from the current time, wrong
relative-date arithmetic, and picking the first of several matching entities instead of asking. "Insufficient
Information" (do not invent arguments when a needed input is missing) is worse: GPT-4o 42.0. A side finding: giving
their user simulator a knowledge boundary and few-shot examples cut simulator hallucination and instruction-following
errors from 18.6 to 7.74 percent.

Transfers? Yes. "14 March" becoming "0003-03-14" is a textbook canonicalization failure on a frontier model.

Actions.
1. Take canonicalization away from the model entirely. Define the tool parameter the model fills as free text in
   the customer's own words (for example promise_date_as_said, amount_as_said) and have the pre-hook parse and
   canonicalize it with the call's reference date; reject anything it cannot parse with an error that names the
   exact question to ask. Impact high for failure (a). Effort medium.
2. Never let the model pick "the first match" for a product or account: route on an extracted enum built from the
   bank's read tool, and make the hook refuse a write whose product is not in the customer's list. Impact medium,
   effort small.
3. Add minefield assertions to review_run: more than one successful write per case, and any "recorded" or
   "confirmed" utterance with no preceding successful write, are automatic failures regardless of the judge.
   Impact medium, effort small.

### 1.3 When2Call

Ross, Mahabaleshwarkar, Suhara (NVIDIA). NAACL 2025, arXiv 2504.18851. https://arxiv.org/abs/2504.18851

Summary. Tests the decision between calling a tool, asking a follow-up question, and declining. When one required
parameter is missing from the user's request, off-the-shelf models call the tool anyway with an invented value:
Llama 3.1 70B 95 percent of the time, Qwen 2.5 72B 34 percent, xLAM 7B 31 percent. Models trained to ask then
over-ask: 10 to 15 percent follow-ups when a call was correct (xLAM 30 percent). The paper's fix is preference
training (RPO), which does not transfer. No prompting-only baseline is reported.

Transfers? The failure pair transfers exactly; the fix does not. The two directions of error are the team's (a) and
(b): invented arguments on one side, one question too many on the other. Any single model sits somewhere on that
trade-off and will not be on the right side of it for every customer.

Actions.
1. Do not let the model make the ask-or-call decision. A code step after extraction checks slot completeness and
   routes either to the "ask for X" node (with the counter) or to the api_request node; the model only speaks the
   question. Impact high for failure (b). Effort medium if any node still lets the model choose.
2. Where the model still fills arguments, the pre-hook rejects placeholder-looking values: empty, "unknown", a
   date equal to today when none was said, a year in the past, an amount of 0. Return what_to_do_next with the
   question. Impact medium, effort small.
3. Make the second ask structurally impossible: once the counter hits the limit, the route lands in a node whose
   prompt contains no instruction to ask and whose only exits are the alternative and the close. The model can
   only over-ask if the node prompt permits it. Impact high for (b), effort small.

### 1.4 Reducing Tool Hallucination via Reliability Alignment (Relign)

Xu et al. ICML 2025, arXiv 2412.04141. https://arxiv.org/abs/2412.04141

Summary. Taxonomy of tool hallucination: selection (wrong or non-existent tool, or "timing": repeating an identical
call) and usage (format: wrong names, types, missing required fields; content: parameter values "invented by the
model" rather than taken from the user). Overall tool hallucination rate on their benchmark: GPT-4o 8.3 percent,
GPT-4o-mini 17.9 percent, GPT-3.5 63.4 percent. Baseline models "tend to favor producing hallucinated outputs rather
than acknowledging failure": in the case study the baseline invented IDs ("project123") and then reported success.
The fix adds explicit TalkToUser and ChangeTools actions and trains for them. A 2025 survey (Lin et al., arXiv
2509.18970) files the same behaviour under "execution hallucinations": the agent claims a sub-step completed when
it did not, with poor tool documentation and lack of "solvability awareness" as listed causes.

Transfers? The taxonomy and the "report success after failure" observation transfer directly to the hackathon's
honesty check (claiming a recording that failed). The RL fix does not.

Actions.
1. Honesty guard in the post-hook: on any non-success response from the bank, set recorded=false and make
   what_to_do_next say, in those words, that the promise was NOT recorded, that the customer must be told so, and
   that the agent must not say it is confirmed; route to a code-produced line. Impact high (honesty check), effort
   small.
2. Idempotency guard in the pre-hook: if an identical write already succeeded in this call, block it and return
   "already recorded, do not call again, confirm to the customer". This is "timing hallucination" and it is also
   the ledger's "recorded once". Impact high, effort small.
3. Give the model a legitimate exit: an enum value such as cannot_proceed that routes to a graceful scripted close,
   so the model has somewhere to go other than fabricating. Impact medium, effort small.

### 1.5 FlowBench

Xiao et al. (Zhejiang University, Alibaba). Findings of EMNLP 2024, arXiv 2406.14884.
https://arxiv.org/abs/2406.14884

Summary. 51 scenarios in 6 domains with workflow knowledge given as text, pseudo-code or a Mermaid flowchart.
Flowchart gives the best turn-level tool F1 for every model (GPT-4o 75.5 vs 66.3 with no workflow), but even with
a workflow GPT-4o's session-level success is 43.2 percent. Removing tool descriptions dropped GPT-4-Turbo's
cross-scenario success from 31.1 to 25.3. With a flowchart, residual session failures are missing steps 49.5
percent and tool usage (wrong tool or parameters) 40.9 percent; sequence errors fall to about 1 percent. Node
prediction (which state am I in) is 92.5 percent single-scenario and 70 to 84 percent cross-scenario, so a model
asked to track its own state is wrong roughly one turn in ten. Their inference prompt enforces one API call per
turn, strict JSON, no arbitrary parameter values, and asking the user to fix invalid input.

Transfers? Partly. A Freya graph removes the "which state am I in" error because the engine holds the state. What
remains is missing steps inside a node and parameter errors, which is what the team still sees.

Actions.
1. Keep each node prompt local: the current state, the one thing to achieve, the allowed exits. Do not paste the
   whole brief into every node; the text-format results show the model loses steps in long policy text. Impact
   medium, effort small.
2. Put their three rules in every tool-bearing node: one tool call per turn, never invent a parameter value, when
   input is invalid ask the customer to correct it. Impact medium, effort small.
3. Keep and improve tool descriptions (a measured 6-point drop without them) and describe parameters in the
   customer's terms, not the bank's. Impact medium, effort small.

### 1.6 SOP-Agent

Ye et al. arXiv 2501.09316, January 2025. https://arxiv.org/abs/2501.09316

Summary. SOPs written as decision graphs (node = action, edge = IF condition or ALWAYS), traversed by selective
depth-first search; at each node the model sees only the function calls of the current sub-nodes. Their Grounded
Customer Service Benchmark covers five industries including banking, 50 SOPs, 5,000 runs. Path accuracy (exact
ground-truth call sequence) 99.8 percent vs 67.4 percent for zero-shot ReAct. Of the 9 failures, 6 were a wrong
branch chosen from an observation and 3 were hallucinated calls. A crude LLM-written SOP scored 84 percent path
accuracy; a manually refined one with "clearer, logically complete conditions" scored 98 percent.

Transfers? Yes. This is the team's architecture evaluated at scale, and the 84 to 98 gap is the most useful number:
the quality of the builder's generated conditions, not the dialogue model, is the ceiling.

Actions.
1. Add a builder self-check on the generated graph: every extraction enum is complete and mutually exclusive,
   every value has a route, and every enum has an "unclear" value that routes to a bounded re-ask. Wrong branch
   choice was two thirds of their residual failures. Impact high, effort medium.
2. Restrict the tools a node can see to the ones legal in that state (SOP-Agent's main structural trick, and the
   Freya format already puts tools on conversation steps). Impact medium, effort small.
3. Wherever the brief gives a threshold, date window or count, compute the branch in code and reserve enum
   extraction for intent only. Impact medium, effort small.

### 1.7 SysBench (with Multi-IF)

Qin et al. (Baichuan, Peking University). ICLR 2025, arXiv 2408.10943. https://arxiv.org/abs/2408.10943
He, Jin et al. (Meta). Multi-IF, arXiv 2410.15553, October 2024. https://arxiv.org/abs/2410.15553

Summary. SysBench: 500 system messages with five user turns each and six constraint types (action, content,
background, role, format, style), verified against checklists. GPT-4o: 87.1 percent of constraints satisfied, 76.4
percent of turns fully satisfied, session stability 54.4 percent. Compliance decays within a session: GPT-4o 84.8
percent on turn one, 33.7 percent by turn five on dependent conversations. Format and action constraints are the
weakest types; background constraints the strongest. Compliance falls further when the user's request conflicts
with the system message. Multi-IF shows the same decay for o1-preview: 0.877 on turn one to 0.707 on turn three.

Transfers? Yes. "Say exactly this sentence" is a format constraint and "ask at most once" is an action constraint,
the two weakest types, and both decay with turn count on every model tested.

Actions.
1. Any sentence the brief wants verbatim is a code-produced line (fixed value via default in vars), never a prompt
   instruction. The team does this for farewells; extend it to every brief-mandated disclosure (identity line,
   recording notice, dispute acknowledgement, refusal wording). Impact high, effort small.
2. Bind rules to the node where they apply, not only to a global prompt; a rule stated fifteen turns earlier has
   roughly half the chance of being followed. Impact medium, effort small.
3. Expect conflict. Hidden customers will push ("just mark it paid", "my friend got a discount"). State the priority
   in the node prompt ("if the customer asks for X, say the fixed line and do not call the tool") and route pushy
   intents to code-gated refusals. Impact medium, effort small.

### 1.8 Towards a Science of AI Agent Reliability (with ReliabilityBench)

Rabanser, Kapoor, Kirgis, Liu, Utpala, Narayanan (Princeton). ICML 2026, arXiv 2602.16666.
https://arxiv.org/abs/2602.16666
Gupta. ReliabilityBench, arXiv 2601.06112, January 2026. https://arxiv.org/abs/2601.06112

Summary. Twelve metrics across consistency, robustness, predictability and safety, measured on 14 models with K=5
runs per task at temperature 0 and J=5 paraphrases per task, on GAIA and a verified 26-task τ-bench airline subset
(24 of the original 50 airline tasks had annotation errors). Accuracy rose steadily over 18 months of releases;
reliability only modestly. Outcome consistency is low for every model. The pattern is "what but not when": across
runs agents choose the same action types but vary their order. On τ-bench, financial accuracy is the most common
policy violation. ReliabilityBench adds that semantically equivalent rephrasing at intensity 0.2 cut success from
96.9 to 88.1 percent and that the simpler architecture (ReAct) was more robust than Reflexion under stress; Khanal
et al. (arXiv 2603.29231, March 2026) find memory scaffolds hurt long-horizon reliability on all 10 models tested.

Transfers? Yes, and it is the strongest external support for the design principle: ordering must be fixed by the
graph, and paraphrase variation is the thing the hidden set adds that reruns of the practice set do not.

Actions.
1. Pin the order of writes in the graph: verification, then promise, then callback, each in its own api_request
   node reached by a route. If two different writes are reachable from one conversation node, split the node.
   Impact high, effort medium.
2. Test with paraphrases, not only reruns: run every practice case in every style the harness offers, and if the
   harness accepts a customer brief, add two reworded variants per case. The hidden set is 60 differently phrased
   people, not 3 reruns of 21 known ones. Impact high, effort small to medium.
3. Keep the architecture simple; no paper in this set found a reliability gain from heavier scaffolding or memory.
   Impact low, effort none.

### 1.9 Justice or Prejudice? Quantifying Biases in LLM-as-a-Judge (CALM)

Ye et al. ICLR 2025, arXiv 2410.02736. https://arxiv.org/abs/2410.02736

Summary. Twelve judge biases measured by principle-guided perturbations of candidate answers. Strongest: position
(with three or more candidates most judges fall below 0.5 robustness), sentiment (emotionally charged wording of a
good answer lowers judge accuracy), distraction (an irrelevant inserted statement shifts the verdict, more so when
the distracted answer was the good one), and self-enhancement. Verbosity cuts both ways: some judges punish length,
some reward it. Fallacy-oversight robustness was high (0.92 to 0.98), so judges do notice broken reasoning. Claude
3.5 was the most resilient judge, GPT-4o close behind. Mitigations are on the judge side (protective phrasing,
randomised order, a different model than the generator).

Transfers? Partly. The team cannot touch the hidden judge, but it writes the transcript the judge reads, and the
three transcript-side biases (sentiment, distraction, verbosity) are all under its control.

Actions.
1. Neutral and short agent turns: no sympathy flourishes, no extra offers, no restating the customer's situation.
   Sentiment and distraction are the two biases most likely to make a literal judge see a policy problem that is
   not there. Impact medium, effort small.
2. Make compliance legible with one plain, code-produced sentence per rule event: "I have recorded your dispute and
   will not ask for a payment today." A judge scanning for the rule finds it, and the model gets no chance to
   paraphrase it into something ambiguous. Impact high, effort small.
3. Never let the agent comment on its own compliance ("that follows our policy"); it reads as distraction and
   invites scrutiny. Impact low, effort none.

### 1.10 Can LLM-as-a-Judge Reliably Verify Rubrics in Agentic Scenarios? (RuVerBench)

Peng et al. EMNLP 2026, arXiv 2606.29920. https://arxiv.org/abs/2606.29920
Supporting: Norman, Rivera, Hughes, "Reliability without Validity", arXiv 2606.19544, June 2026.
https://arxiv.org/abs/2606.19544

Summary. 2,458 human-labelled (output, rubric) pairs from deep research and agentic coding. The best judges reach 85
to 95 balanced accuracy; humans against adjudicated labels reach 90 to 94. "Rules" and "Tools" rubrics are the
hardest categories in the agentic setting (Claude Sonnet 4.6 scores 72.1 on Tools). Judges err in different
directions: GPT-5.4 is strict and turns optional conditions into requirements; Gemini 3.1 and Claude Opus 4.7 are
permissive and miss missing steps. Error sets overlap little across judges (16 to 21 percent). Batching four or
five rubrics in one call costs double digits; majority voting helps and levels off at three to five votes. Norman
et al. find judge test-retest consistency above 0.95 yet chance-corrected agreement 33 to 41 points below raw
agreement, so a judge can be perfectly repeatable and still wrong. Dongre et al. (entry 2.4) find a three-judge
ensemble at 84 percent accuracy on compliant / partial / violation labels with human inter-rater alpha only 0.63.

Transfers? Yes for the team's own review loop. For the hidden judge the lesson is that borderline turns are coin
flips, so the lever is to remove borderline behaviour, not to argue with the judge.

Actions.
1. Review loop: judge one rule per call, never a batch of rules, and take three votes before treating a judge
   failure as an agent bug. This separates failure (c) from real faults. Impact medium, effort small.
2. Assume a strict judge: where the brief says "may" or "should consider", do it anyway in a fixed line if it is
   cheap, because strict judges convert optional into required. Impact medium, effort small.
3. Accept that 5 to 15 percent of verdicts on genuinely ambiguous turns go either way, and put the facts a judge
   needs (product, amount, date) in the confirmation line so the turn is not ambiguous. Impact medium, effort
   small.

## 2. Supporting sources (short)

### 2.1 StateFlow
Wu, Yue, Zhang, Wang, Wu. arXiv 2403.11322, 2024. https://arxiv.org/abs/2403.11322
State-machine agent beats ReAct by 13 to 28 points (InterCode SQL 63.7 vs 50.7, ALFWorld 83.3 vs 55.5) at three to
five times lower cost. Prefers string-matching transitions where output is structured and reserves LLM judgement
for ambiguous cases; recommends an explicit Error state and short state-specific prompts. Action: an explicit
error-recovery node after each api_request (feeds the honesty guard in 1.4). Impact medium, effort small.

### 2.2 AgentSpec
Wang, Poskitt, Sun (SMU). ICSE 2026, arXiv 2503.18666. https://arxiv.org/abs/2503.18666
Runtime rules of the form trigger / check / enforce (user_inspection, stop, invoke_action) evaluated before an
action, with millisecond overhead; its motivating example is "confirm before a financial transaction". The number
that matters: o1-generated rules reached 95.6 percent precision but 71 percent recall. Action: the builder's weak
spot is recall, so write a machine check that every numbered rule in the brief maps to a hook, a route or a fixed
line, record the table in the trace, and fail the build if a rule has no home. Impact high if not already
automated, effort small.

### 2.3 IntellAgent
Levi, Kadar (Plurai). arXiv 2501.11067, January 2025. https://arxiv.org/abs/2501.11067
Policy-graph generated conversational tests; correlates 0.92 to 0.98 with τ-bench. Success declines with the
number of interacting policies in one event, and "all models face challenges with user consent policies". Action:
consent before any write is a code gate on an extracted explicit yes, never a model judgement; and practice
cases should stack two or three policies (dispute plus partial amount plus callback) because that is where
success drops. Impact high for consent, effort small.

### 2.4 When Attention Closes: How LLMs Lose the Thread in Multi-Turn Interaction
Dongre, Hsieh, Lai, Yoon, Bui, Hakkani-Tür. arXiv 2605.12922, May 2026 (v2 October 2026).
https://arxiv.org/abs/2605.12922
Measures attention from generated tokens to goal-defining tokens over 50-turn conversations in open 7B to 8x7B
models. The channel closes around turn 19 to 23; after it, persona-rule violations converge to 47 to 58 percent
even without user pressure. Appendix H reports a negative result for periodically re-injecting the goal text as a
user turn: "repeating or retaining text is not equivalent to preserving goal information". Transfer is partial
(weaker open models), but the direction holds. Action: keep calls short by design (route to close as soon as the
ledger goal is met), and do not rely on "remind the model of the rules every turn" as the fix for late-call
violations; put the rule in the node that needs it and gate the action in code. Impact medium, effort small.

### 2.5 Writing effective tools for agents, with agents
Anthropic engineering blog, September 2025. https://www.anthropic.com/engineering/writing-tools-for-agents
Practitioner guidance from measured tool evaluations: write descriptions as if onboarding a new hire; unambiguous
parameter names (user_id, not user); strict input models; error messages that say what to fix and show a correctly
formatted input; resolve cryptic IDs into readable names in responses; small description changes moved SWE-bench
Verified results. Action: every hook rejection should carry a correctly formatted example and the exact question to
ask, and tool responses mapped into the conversation should use product names, not IDs. Impact medium, effort small.

### 2.6 Multi-IF
Covered in 1.7. Instruction following decays by turn on all 14 models tested.

### 2.7 ReliabilityBench and Beyond pass@1
Covered in 1.8. Paraphrase robustness and simpler-is-more-robust.

### 2.8 Agent hallucination survey
Lin et al., arXiv 2509.18970, September 2025. Covered in 1.4. Execution hallucination = claiming a step completed.

## 3. Where the literature qualifies the current design principle

The principle "move the decision from the model into code" is supported by every source above that measures it
(SOP-Agent, StateFlow, FlowBench, Princeton, AgentSpec). Five qualifications:

1. Rigid routing has its own failure mode. SOP-Agent's residual failures were two thirds wrong branch choice, and
   Princeton notes rigid trajectories trade adaptability for auditability. An enum route is only as good as the
   extraction behind it. Mitigation: every enum has an "unclear" value with a bounded re-ask, and the self-test
   deliberately feeds ambiguous turns to confirm the graph recovers instead of dead-ending.

2. Restating policy each turn is not the fix; restating state is. When Attention Closes reports a negative result
   for re-injecting goal text, and Liu et al. find naive summaries nearly useless, while the Mediator (an imperative
   restatement of the consolidated state) recovers 20 points. So what_to_do_next should be an instruction built
   from vars ("ask only for the year"), not a recap of the brief.

3. "Always call the tool even with partial input" is safe only if the hook treats the call as a validation request.
   ToolSandbox and When2Call show models invent the missing value rather than leave it blank; if the team adopts
   always-call, the pre-hook must never forward a partial or placeholder argument to the bank and must return the
   question instead. This is consistent with the current hooks, but worth stating as a rule in the skill.

4. Clarifying questions cut both ways. Liu et al. argue users want provisional answers; When2Call shows askers
   over-ask. In this domain the brief decides, so the counter approach is right, but the decision to ask should
   be made once by code, and the question wording should be fixed, so the model never judges whether to ask.

5. More explanation can hurt with a judge. CALM's distraction and verbosity findings mean "explaining compliance"
   at length can lower judge accuracy. One fixed, plain sentence per rule event is the right dose; a paragraph is
   not.

Honesty problems judges flag, from the sources: claiming a step completed when the tool failed (Relign, the
hallucination survey, the hackathon page), inventing an argument and reporting success on it (Relign case study),
and restating a fact in a different form than the customer gave it (Lost in Conversation lock-in). All three are
removed by the same two guards: code-canonicalized arguments and a post-hook that scripts the confirmation from
the bank's actual response.

## 4. Ranked top five

1. Canonicalize in code, never in the model: tool parameters take the customer's words, the pre-hook parses dates,
   amounts and products against the call date and an enum of the customer's products, and rejects anything else
   with the exact question to ask (ToolSandbox; Lost in Conversation).
2. Make ask-or-call a code decision: a slot-completeness check plus the counter chooses between the re-ask node and
   the api_request node, and the capped node has no instruction to ask, so one-question-too-many becomes
   structurally impossible (When2Call; SOP-Agent).
3. Honesty and idempotency guards in hooks: on any non-success response, what_to_do_next says the promise was NOT
   recorded in those words and routes to a scripted line; an identical successful write earlier in the call blocks
   the second one; the confirmation sentence is built in code from the bank's response (Relign; Princeton "what but
   not when").
4. Feed the model a one-line imperative restatement of the consolidated state each turn ("Known: 150, 14 March.
   Ask only for the year.") instead of raw partial answers or policy reminders (Intent Mismatch Mediator; Lost in
   Conversation snowball; When Attention Closes negative result on re-injection).
5. Judge-proof the transcript and the review loop: short neutral turns, one code-produced sentence per rule event
   that names product, amount and date, every verbatim disclosure as a fixed line; and in review_run, one rule per
   judge call with three votes before a judge failure counts as an agent bug (CALM; RuVerBench; SysBench).

Next two if there is time: paraphrase testing across every style and two reworded variants per practice case
(Princeton; ReliabilityBench), and a machine check that every numbered brief rule has a home in a hook, route or
fixed line, recorded in the trace (AgentSpec recall finding).
