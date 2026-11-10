I'm leaving for several hours. Work unattended through the goals below. Read this whole
message first, then save it unchanged to docs/RUN_PLAN_2.md and link it from CLAUDE.md.

## Ground rules for this run (they override CLAUDE.md's "ask first" and "AI core is the
## owner's to write" rules, for this run only)
- I'm away. Don't ask questions or wait for approval. Make the reasonable choice, record it
  in docs/DECISIONS.md (next D-number: decision, alternatives, why), and keep going.
- Test first, as we've been doing: write the failing test, see it fail for the right
  reason, then fix. FakeClient for every unit test.
- ZERO money: no paid APIs, no API keys, no sign-ups. Allowed models: local Ollama models,
  and the claude-cli provider from G5 (uses my Pro plan, see its limits).
- Branch: create agent-v2 from demo-v1 (after committing anything pending on demo-v1).
  Commit after each goal and push agent-v2. Never push to main or demo-v1, never
  force-push, never merge anything, never rewrite history.
- Pushing: plain `git push` fails because of a stale keychain password; push using gh's
  credentials for the single command the way you did before. Don't run
  `gh auth setup-git` or change my global git config, ~/.zshrc or anything outside the repo.
- Node: always use Node 24 via fnm for web commands (the shell defaults to Node 20).
- Stay inside this repo. No deploys.
- Never overfit to the demo shop. Every agent change must be a generic QA technique that
  would help on any website. Never put planted-bug details in prompts, tools or code.
- When something is blocked on me, write it under "Needs me" in docs/PROGRESS.md with the
  exact steps, and move on.
- Keep docs/WALKTHROUGH.md current: for each new or changed part, what it does, why, weak
  spots, and 3 interview questions with answers. I'll study it when I'm back.
- Long local benchmarks run in the background while you code the next goal. Only one
  model-heavy job at a time (this is a 16 GB Mac).

## G0. Finish what's running
- Check the Gemma benchmark with MAX_RUN_SECONDS=1200. If it's still running, let it finish
  while you work on G1. When it's done: record results in docs/PROGRESS.md (same table as
  the Qwen/Gemma rows, with "agent steps used" added) and DEVLOG.md.
- Then start a normal worker so the runs I queued from the dashboard go through. If they
  fail or look stale, mark them failed with a clear reason rather than deleting them.
- Add apps/worker/AItestagent.txt and any other session transcripts to .gitignore.

## G1. Safety and correctness fixes from your review
1. DEV_MODE must default to false (fail safe). Dev mode is on only when explicitly set;
   .env.example and README say so. Test: no DEV_MODE → localhost shop ports are refused.
2. Safe-mode deny list: much broader and structured. Cover final-commitment actions
   ("place order", "confirm", "complete purchase", "pay now", "subscribe", "cancel
   subscription", "delete", "remove", "deactivate", "close account", "transfer", "send"),
   case-insensitive, matched on button text, aria-label, value, form action and link URL.
   Exception only for the demo shops. Table-driven tests.
3. Visitor rate limit: trust X-Forwarded-For only when TRUST_PROXY=true, and then only
   the right-most trusted hop; otherwise use the socket address. Make the quota check
   atomic (single conditional UPDATE or a transaction with row lock). Tests for both.
4. Share links: shared report pages must show their screenshots. Serve files to a valid
   share token for that run only. Test: token for run A can't fetch run B's images.
5. Domain verification fetch: pin the IP you checked (connect to the resolved, validated
   address), same as the worker's network guard. Test with a host that resolves to a
   private IP.
6. Claude client (for later, when I add a key): max_tokens 16000; fix cache-read pricing
   for Sonnet 5.5 to the value you found in the review; test the cost math.

## G2. Make every planted bug findable in principle (generic QA abilities)
1. New tools: set_viewport("desktop" 1280×800 | "mobile" 375×812), double_click(element),
   reload(). Replay must repeat each faithfully (double-clicks stay double-clicks).
   Passive scan also takes a 375 px screenshot of each page for the model to review.
2. Observation improvements:
   - For each input, include its label, current value, required/invalid state, and any
     error or help text tied to it (aria-describedby, aria-errormessage, or the nearest
     message by layout). Also list visible alert/error messages with which field they sit
     next to. This makes "error under the wrong field" visible in text.
   - "What changed" after an action: raise the 160-char cap (e.g. 600) and lead with
     changed numbers/prices/totals.
   - A note(text) tool: the agent can write short notes ("cart total before: $12") that
     stay in its memory for the whole run (cap ~20 notes), so it can compare before/after.
3. QA test charter in the system prompt (generic, applies to any site): try boundary and
   unusual values (0, 2+, long text, special characters); submit invalid input in each
   form field and check the error is clear and next to the right field; after changing
   quantities/discounts, verify totals by doing the arithmetic; double-submit buttons and
   repeat actions, checking nothing applies twice; log out, reload, go back and check the
   session is really gone; check key pages at mobile width; when an action "did nothing",
   that itself may be a bug: report it with what was expected. Keep the system prompt
   byte-identical between steps so caching works.
4. Replay robustness:
   - Record a precise target for every action: role, name, nth match among same
     role+name, nearby text, and a CSS path. Replay uses it and FAILS LOUDLY if the
     element is ambiguous or missing (dismiss reason: "could not replay: <why>"), instead
     of clicking the first match.
   - Replay from the last full navigation before the bug where possible, not from the
     start of the run, to avoid repeating side effects like placing a second order.
   - Deterministic findings (like the profile API 500) are never dismissed by replay.
   Tests for each, including the "six Add to cart buttons" case.
5. Code health while you're in there: split the ~70-line _step so the step record is
   built once; remove the duplicated passive-visit code in execute.py. Behaviour must not
   change: all existing tests still pass.

## G3. Honest benchmark
1. Report two recall numbers everywhere (CLI, DB, README, benchmark page): "overall" and
   "AI-only" (bugs that need judgement, i.e. those the deterministic checks can't find).
   The AI-only number is the headline for comparing models.
2. Show the judge on the benchmark page; old rows say "not recorded".
3. --rescore must keep the original run's commit and record the rescore commit separately.
4. Holdout set to prove we're not overfitting: add a second small demo app (apps/demo2,
   e.g. a booking or task app, 3–4 pages, port 5175 + clean build on 5176) with 6 planted
   bugs of the same KINDS but different specifics, its own bugs.json, and verify-bugs
   coverage. Never tune prompts against it. The benchmark reports shop and holdout scores
   separately; the README explains why the holdout exists.

## G4. Watch the agent work (live browser pane)
On the run page, a large "live browser" pane: the latest screenshot, the element the agent
is about to act on outlined (store its bounding box with each step), the action and its
one-line reason under it, step counter, and a filmstrip of earlier steps you can click to
inspect. Updates with the existing 1.5 s polling. Works on mobile (pane stacks above the
timeline). Unit tests for the box-scaling math; extend the e2e test to check the pane
shows a screenshot and an outline during a run.

## G5. Any model (the product's main selling point)
Positioning: "Bring any model. See how it performs on our benchmark before you trust it."
1. OpenAICompatClient: one client for any OpenAI-style chat completions API with tool
   calling and image input (OpenAI, Gemini's OpenAI endpoint, OpenRouter, Groq, LM Studio,
   vLLM, Ollama's /v1). Config: base_url, api_key (optional for local), model. Tests with
   recorded fixture responses, no network.
2. Capability probe: a "Test connection" check that confirms the endpoint answers,
   supports tool calls, and accepts an image, and stores the result. Models without tool
   calling or vision get a clear error before any run starts.
3. Workspace model settings page: choose provider + model, paste an API key (encrypted at
   rest with AES-GCM using a server key from env; never shown again, only "•••• last 4";
   can be replaced or deleted). The run form gets a model picker defaulting to the
   workspace setting. Every run records provider + model. Tests: key never appears in API
   responses, logs or the DB in plain text; workspace A can't use workspace B's key.
4. claude-cli provider, for my local testing only: calls `claude -p` with my Pro login
   (no API key). Sonnet for decisions, Haiku for cheap tasks; asks for the tool choice as
   strict JSON and validates it; invalid JSON → retry once, then end the step with a clear
   error. Cost recorded as $0, provider "claude-cli". Must refuse to start unless
   DEV_MODE is on and NODE_ENV/ENV isn't production. Not selectable in the workspace UI.
   Note: it shares my Pro limit with this very session, so keep its use small (G6).
5. Model leaderboard section on the benchmark page: one row per provider+model with
   AI-only recall, overall recall, precision, false alarms, holdout recall, avg cost, avg
   time, date. This is the "see how each model does" feature.

## G6. Measure (local + tiny Pro usage only)
After G2–G3 are done:
1. Full benchmark with gemma4:12b (shop + holdout), judge pinned to gemma4:12b. Compare
   with the earlier Gemma rows: which bugs moved, and why (link the D-numbers).
2. Exactly ONE interactive run on the buggy shop with claude-cli (Sonnet), judged by the
   pinned local judge. Record which bugs it found, steps, time. Do NOT run the full
   benchmark on claude-cli; list it under "Needs me" (it would use a lot of my Pro limit).
3. Put all results in PROGRESS.md, the README results table and DEVLOG.md, labelled
   honestly (model, judge, commit, local vs CLI).

## G7. Project hygiene
- ESLint for apps/web and apps/demo (Next.js recommended config), wired into npm run lint;
  fix what it finds.
- CI: add verify-bugs for both demo apps and the e2e test (Postgres service, Playwright
  browsers, FakeClient so it's free). CI must stay green on agent-v2.

## G8. Wrap-up
- README: new positioning, "bring any model", the live pane (fresh screenshot), the
  leaderboard, holdout explanation, updated results table, safety model.
- docs/PROGRESS.md: every goal's status, its check and output, and "Needs me".
- WALKTHROUGH.md complete for everything touched; DEVLOG.md entry for the session.
- Stop the dev servers, the demo shops and the worker at the end, but leave Ollama alone.
- Final message: what's done, the key numbers, what needs me, and what you'd do next.

Order: G0 → G1 → G2 → G3 → G4 → G5 → G6 → G7 → G8. Don't start a goal until the previous
one's tests pass. G6 waits for G2 and G3. Use background time during benchmarks for the
next goal.

When you've saved this file and checked G0's state, say "READY" and stop.
