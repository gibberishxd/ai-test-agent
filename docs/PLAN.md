# Plan

An AI agent that explores a web app like a manual tester and reports bugs with screenshots and
repro steps. The selling point: it measures its own accuracy against a demo shop with planted
bugs (recall, precision, cost per run) and improves over versions.

## Decisions already made

- Python worker (uv, Playwright, pytest, ruff); TypeScript Next.js web app; Vite + React demo shop.
- Web app and worker talk ONLY through Postgres: a `runs` table that the worker claims with
  `SELECT ... FOR UPDATE SKIP LOCKED`. No Redis or BullMQ.
- LLM: Claude API with tool use + vision.
- Demo target: a small shop (products, cart, checkout, login, profile), plus a clean copy with no
  bugs to measure false alarms.

## Roadmap

Each phase ends in something that works. Don't start a phase before the previous one's
"done when" is true.

0. **Repo setup.** DONE.
1. **Deterministic checker (no AI):** crawl same-origin pages, collect console errors, failed
   requests, HTTP 4xx/5xx, broken links, axe-core accessibility violations, a screenshot per page,
   and write a typed JSON report.
   *Done when:* running it on the demo app produces a report.
2. **Demo shop + benchmark:** plant ~12 bugs, describe them in `bugs.json`, and add `make bench`,
   which prints found / missed / false alarms. The owner writes the bug list.
3. **AI agent loop:** observe (accessibility tree + screenshot) → Claude picks one action via tools
   (click, type, navigate, report_bug, finish) → execute → log, with a step budget.
   The owner writes the loop, the system prompt and the bug judging; Claude reviews and explains.
4. **Cut false alarms:** replay each candidate bug in a fresh browser, deduplicate, compare
   benchmark scores with Phase 3.
5. **Fullstack:** dashboard (start a run, live progress, bug report), Postgres schema, deploy
   (web on Vercel; worker + Postgres on Railway or Fly.io).
6. **Eval dashboard** charting scores across versions, README, write-up, 2-minute demo video.

## Future ideas (after Phase 6, not before)

**The pitch for businesses:** "give us a URL, get bugs you can trust." Black-box testing, with no
code access or SDK needed, and accuracy you can prove with the benchmark (precision, recall, cost
per run). Most testing tools can't show false-alarm rates; this one can.

What customers would need beyond the roadmap: login and test accounts, staging environments,
running in CI on every deploy, predictable cost per run.

**Phase 7 idea: security hygiene checks.** Small deterministic checks built on the network
responses Phase 1 already captures:
- exposed source maps (the original source code is served publicly)
- secrets or API keys in JS bundles
- outdated frontend libraries with known vulnerabilities
- missing security headers (CSP, HSTS, X-Content-Type-Options)

**Decided against:** building on reverse-engineering toolkits such as morluto/rea. They target a
different problem (security research), need written authorization from the site owner, would fail
enterprise vendor security reviews, and would replace work this project should show as its own.
