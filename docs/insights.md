# Ten insights, with the evidence and the limit of each claim

> Note added 19:35 Sunday. At 17:59 the live hackathon page was found to define the final differently from the kit README:
> one case, Freya Bank's card statement-debt line in Turkish, delivered as a zip of documents, with a bank mock the team
> hosts on Cloudflare Workers and a `submission.json` carrying the mock's address. The builder was extended for that form
> between 18:00 and 19:11 (commits 4779c60 to e58ca6e, tag `submission-candidate` at 0e3ccdc, 77 tests); its English
> behaviour was verified identical on every practice case, and a Turkish document set built in 144 s and passed a Turkish
> chat probe against the live mock at 19:00. Every measurement below was taken on the English practice briefs. The run
> command is now `python3 builder/build.py <document folder> <mock url>`; the runbook is `docs/runbook-final.md`.

1. **Consistency is a different goal from accuracy.** Under pass-all-three, an agent right 90% of the time gives 73% of
   customers, one right 80% gives 51%. Evidence: arithmetic; our first three-repetition run scored 17 of 21 with 18, 19
   and 20 per repetition (tracker run 4). Limit: the hidden set may have families our 21 cases do not.

2. **Every flaky case was a decision the model made that code could make.** Counting asks, converting dates, joining
   split answers, naming the end reason, computing the outcome. Sixteen moves, each followed by three of three on the
   case (tracker log l18 to l51). Limit: the moves that remain, multi-product negotiation above all, are the ones where
   the decision depends on the conversation's shape and not on a value.

3. **Read the whole brief into a schema, then render; do not let the model write the workflow.** The paper's builders
   that searched documents missed rules; ours reads every line into one policy with the rules verbatim, and the
   renderer puts each rule where it is most reliable. Evidence: 47 of 47 Brief A rules captured on the first build
   (log l05); two unseen banks rendered correctly (Northwind 13 of 13 three of three; Harbor through the dry run).
   Limit: a rule shape the schema cannot hold (a deadline in calendar days, a callback window by weekday) is reduced
   to the nearest shape; the trace says which.

4. **A tool result is the best place to tell the model what to do next.** Every post-hook writes one imperative
   sentence built from variables ("ask only for the year"; "already recorded, do not call again"). Evidence: the
   silent-after-tool-result failure disappeared after this (log l06, l12). Limit: it cannot force speech between two
   tool calls the model makes in one turn (the silent retry).

5. **A blocked call must still get a 200.** The platform sends the request even with an empty body and skips the
   post-hook on an error, so a blocked call sends values no bank accepts: the bank records nothing and the hook can
   speak. Evidence: log l40, verified against the bank directly. Limit: depends on the bank answering a validation
   error with ok false rather than a 4xx; the practice mock does.

6. **Hidden briefs change the tool fields, not only the values.** Hooks that read `amount` by name block every
   promise on a bank that calls it `promised_sum`. Reading the names from the API file at build time, with the
   model filling a role map and a keyword fallback, cost nothing on the known files and worked first time on a
   renamed one (commit de0a864, tests/test_render.py, log l57). Limit: a field no keyword and no model finds leaves
   the role name, which the trace reports.

7. **Measure the platform before blaming the agent.** Two outages, a sandbox fault near 1%, judge variance near 3%,
   persona lines cut short, customers hanging up on a slow model. Each has a signature in the call's events; the
   runner and the review loop print it. Evidence: results/review-run37-reps3.md, run38, log l48, l53, l59, l61.
   Limit: the organizers' platform at scoring time is the same software under their load, not ours.

8. **Retries belong in one place, and every one of them earned its line on Sunday.** A status poll 504 orphaned a
   simulation; a seven-minute hang killed a build at its save; a 404 on a deleted simulation would have waited forty
   minutes. Each is now a few lines in the wrapper or the build, found by letting the real platform misbehave
   against the real tooling (commits 0d9b939, 89b0409, 8e0662f, da9b23a, 318dac2). Limit: a build still cannot
   finish if the platform never answers a save in 27 minutes; it then raises with the trace saying why.

9. **A threshold is only a decision when both of its failure modes are known.** Raising the opening's confirmation
   confidence from 0.6 to 0.8 after a cut-off line passed as a "yes" looked right for an hour; the next run showed
   the extractor missing a plain yes outright, which a higher bar turns into a second ask that a questioning customer
   fails. Reverted on evidence (commits a957516, 0968f39, log l64). Limit: the real fix, a fixed re-ask line and a
   second independent extraction, is unmeasured.

10. **Negative results worth keeping.** Restating the policy every turn does not help; restating the consolidated
    state as one instruction does (docs/research-edge.md, section 3). Temperature does not fix multi-turn variance.
    Memory scaffolds hurt long-horizon reliability in the one study that measured them. And a judge reads short
    neutral turns better than compliance talk, so the fixed lines stay short. Limit: these come from papers on other
    tasks; what transferred here is the design, not the numbers.
