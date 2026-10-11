# Figures for the write-up and the stakeholder deck

Hand-written SVG (standard library only, no external fonts or scripts), 1200 px wide, white background,
colour-blind-safe palette: blue `#1f4bd8`, green `#167a4a`, amber `#9a5b00`, red `#b4232b`, grey `#5b6473`.
Data for figures 2 to 4 is the run series of 10 to 11 October 2026 (Istanbul time); figure 1 is built from
`brief-a.workflow.json` (Brief A agent, workflow v52), no node invented.

**Figure 1, `fig1-architecture.svg`.** The Brief A phone agent as a graph: 40 steps in six phase bands in call
order (Opening and right person 10, Identity 4, Account facts 2, Negotiation 6, Bank writes 3, Close 15), 65
distinct transitions (67 in the file; two source-target pairs carry two conditions). Each box shows the step id,
its type (conversation, code, api_request, end_call), the tool count on conversation steps and a `hook` badge
where a step has a pre/post action or its tools carry pre/post process code. Unlabelled arrows are `always`;
`equals` and `is_tool_call` label the routed ones. Phase assignment by id, with these nearest-group choices:
`mark_confirmed`, `third_party_prep`, `outcome_wrong_number`, `outcome_deceased`, `outcome_unclear` and
`outcome_unclear_quiet` go to Opening; `outcome_id_failed`, `outcome_id_declined`, `outcome_id_declined_quiet`
to Identity; `count_refusal` to Negotiation; `outcome_callback`, `outcome_no_callback`,
`outcome_no_callback_quiet` to Bank writes; `end_*`, `hang_up_*` and `close` to Close. `outcome_unclear_quiet`
has no incoming transition in v52 and is drawn as an unconnected box.

**Figure 2, `fig2-results.svg`.** Main series: customers passed in all 3 of 3 repetitions (of 21) by agent
version, runs 4 to 35. Per-repetition counts sit under each point; amber points (runs 7, 24, 33) are the runs
whose misses were platform or judge losses, not agent errors; the numbered list below the chart gives the fix
that went in before each run. Run 35 (v52) is shown as an open point in a "not yet scored" strip, running at the
time of drawing, so it never reads as a value.

**Figure 3, `fig3-robustness.svg`.** Three panels: (a) speaking styles by version (pieces 16, 18, 19, 20, 19 of
21, the last under 3 repetitions at v46; corrects 20, 19, 21; in_words 21), (b) Friday 16 Oct and holiday eve
23 Oct at v28 and v46, (c) the Northwind variant bank (13/13 first build, 11/13 rebuilt in 3 of 3, 13/13 with
the refusal count in code in 3 of 3, 13/13 final code). Light tracks show the set size; hatched amber bars are
the ones whose misses were platform or simulator losses, explained in the notes under the chart.

**Figure 4, `fig4-decisions.svg`.** Timeline, Sat 23:50 to Sun 11:14, of the 16 decisions moved from the model
into structure, one row per decision with a marker coloured and shaped by its new home (code step 4, hook 7,
route 2, structure or fixed line 2, prompt 1; counts in the inset). Red and amber are close under deutan vision,
so the home is also encoded by marker shape and written on every row.
