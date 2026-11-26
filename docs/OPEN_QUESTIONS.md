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
   **Done (2026-11-26, the owner's step 3, D121):** deep runs now turn them into deterministic
   findings, as the loop does.
4. **Keyboard-probe steps aren't replayed.** Their key presses leave a state replay can't rebuild,
   so later replay steps can diverge. Choice: probes are evidence only; a keyboard finding is
   verified by probing the same control again in a fresh browser.
5. **A resumed run's browser state.** A resumed run starts the browser fresh on the target (a cart
   or sign-in is gone; a saved login setup signs in again). Choice: the resume prompt tells the
   model to rebuild what it needs.
6. **Carrying fixes up the stacked branches: rebase or merge?** The owner asked for a rebase of
   the branches above a fix, but every `deep-*` branch is already pushed, so a rebase needs a
   force-push, which the same instructions stop on. Choice: merge the fixed branch into the one
   above it, in order (as the stack was updated before: "Merge branch 'deep-run' into
   deep-web"). The history is busier, nothing is rewritten. A rebase can still be done at merge
   time.
7. **Errors logged before a pause.** D121's per-page error log lives in the toolbox, so a run that
   pauses on a usage limit loses what it logged before the pause; only errors seen after the
   resume become findings. Choice: accepted for now (pauses are rare, and the crawl's findings and
   the model's own reports are kept). Saving the log with the coverage is a small change if
   wanted.
8. **A clipboard error caused by our test browser.** On IT-Tools, a deep run that clicks a "copy"
   button gets "Uncaught exception: NotAllowedError: Failed to execute 'writeText' on 'Clipboard'",
   which D121 now reports as a deterministic finding. A real user's browser allows `writeText`
   after a click; ours has no clipboard permission, so this is the harness's error, not the
   site's. Choice: not changed in run 9 (the browser context is shared with the loop and the
   crawl). The likely fix is to grant `clipboard-read`/`clipboard-write` in the guarded context
   for every engine, measured on the benchmarks like any change. Until then, count it as a
   false alarm when it shows.
9. **Scoring a paused run: a candidate counts as "verified".** `benchmark.stage_of` treats every
   report that isn't dismissed, a duplicate or unverified as verified, including candidates whose
   verification hasn't run because the run paused. The real-world runner then prints "found" for
   a paused run (IT-5, 2026-11-26). Choice: not changed (matching and scoring are the owner's);
   a paused run is re-scored after it is resumed and verified, and its first, provisional row in
   `apps/realworld/results.jsonl` is marked as such in `docs/REAL_WORLD.md`. A one-line fix would
   be `if bug.status == "candidate": return "candidate", None`.

