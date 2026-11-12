# Run 3 plan (branch `agent-v3`, unattended)

The owner's goals for run 3 (summarised from their message), each with the acceptance check I
will run, in the order I will do them. Rules carried over from `docs/RUN_PLAN_2.md` and
`CLAUDE.md`: no questions (decisions go to `docs/DECISIONS.md`), test first, zero money, no
merges, no force-push, push `agent-v3` after each goal with gh's credentials for that one
command, Node 24 via fnm, stay inside the repo, never put planted-bug details into the agent.

Extra rules for run 3:
- `SONNET_RUNS_ALLOWED = 1`: at most one full claude-cli benchmark run, in H7 only, after
  H0–H6 are committed. On a usage limit: stop, record, don't retry.
- claude-cli only from a temp folder outside the repo, file access limited to that folder;
  checked before every call.
- `npm test` and `npm run lint` exit 0 from the root before each commit.
- Earlier benchmark results are never deleted or rewritten; new ones are added beside them.
- Blocked ~90 minutes → write it under "Needs me" and move on.

| Goal | What | Acceptance check |
|---|---|---|
| H0 | This plan; services up; baseline green on the new branch | `npm test` + `npm run lint` exit 0 on `agent-v3` before any change |
| H1 | Fix replay discarding correct reports | A failing test that replays reports one after another where the first leaves state behind, then passes after the fix; every replay failure stores a specific reason; offline re-verification of run be495c9f's stored steps (no model calls) verifies bugs 5 and 8 and loses no previously verified report; before/after recorded |
| H2 | Show what verification throws away | Unit tests (written first) for: reported, verified, discarded at replay (by reason), matched before/after verification, "correct but discarded", false alarms; shown in `bench` output and on the leaderboard; false alarms measured for claude-cli too |
| H3 | Demo sign-in flake | A loop script signing in 50 times shows the failure before the fix (or the cause is shown by a test), 0 of 50 after; the e2e retry helper removed; e2e passes |
| H4 | Database hardening | ≥ 4 concurrent workers on many queued runs: each claimed exactly once (test); crashed-worker runs are recovered by a lease timeout (tests); EXPLAIN ANALYZE before/after on seeded volume (10k runs, 500k events) for the hot queries, indexes only where the plan improves; `docs/DATABASE.md` with ER diagram, tables, keys, indexes, queue design, Prisma/SQLAlchemy sync, migrations; schema changes via Prisma migration + SQLAlchemy mirror + drift test |
| H5 | CI cleanup | No Node 20 deprecation warnings in the CI log; CI green on `agent-v3` |
| H6 | Free re-measurement with Gemma + miss analysis | Gemma 12B benchmark, shop + holdout, `MAX_RUN_SECONDS=1200`, judge gemma4:12b, recorded beside run 2's; `docs/MISS_ANALYSIS.md` covers every AI-only planted bug in both apps with the reason from the traces; any agent change is generic and does not lower holdout results |
| H7 | One Sonnet benchmark run (claude-cli) | Only after H0–H6 are pushed; shop, same settings as be495c9f, safe temp folder; AI-only, overall, correct-but-discarded, false alarms, compared with be495c9f; holdout only if limits allow |
| H8 | Wrap-up | README results table, WALKTHROUGH, PROGRESS (done / Needs me), DEVLOG (suggested lines), DECISIONS; `npm test` + `npm run lint` exit 0; CI green; pushed; servers stopped, Ollama left running; short final message |
