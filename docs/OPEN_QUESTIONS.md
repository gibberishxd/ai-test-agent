# Open questions

Questions that came up during work the owner asked to be done without stopping. Each one has the
choice that was made so work could continue; the owner can overrule any of them.

Format: the question, the choice made, and why. Newest last.

## Run 9 (deep mode)

1. **Do plans cap deep runs?** Plans have a per-run step limit for the current loop (`consume_quota`'s
   `max_steps`, e.g. 40 on free). Choice: it doesn't apply to deep runs; their limits are the
   workspace's (default 400 steps, 60 minutes), lowered only by the run's own. Why: quality first
   (D111), and the customer pays the model with their own key. A plan limit for deep runs is a
   pricing decision.
2. **The benchmark's cost cap with deep runs.** `BENCH_MAX_COST_USD` (default $5, API-equivalent)
   still stops a benchmark, and a deep run can pass it alone. Choice: unchanged; for deep
   evaluation runs set `BENCH_MAX_COST_USD=0` (no cap) or a value you choose, once you approve the
   cost. A paused run stops the benchmark either way.
3. **Console and network errors from deep runs as deterministic findings.** The loop turns errors
   it saw while clicking into findings; deep mode doesn't yet (its log isn't kept per page).
   Choice: not in run 9; the model has console and network tools and a checklist area for them,
   and the crawl's deterministic findings stay.
4. **Keyboard-probe steps aren't replayed.** Their key presses leave a state replay can't rebuild,
   so later replay steps can diverge. Choice: probes are evidence only; a keyboard finding is
   verified by probing the same control again in a fresh browser.
5. **A resumed run's browser state.** A resumed run starts the browser fresh on the target (a cart
   or sign-in is gone; a saved login setup signs in again). Choice: the resume prompt tells the
   model to rebuild what it needs.
