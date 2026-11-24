# Run 9 plan: deep mode (stacked branches `deep-*`)

Goal: a second agent engine, **deep mode**, next to the current loop, aimed at finding as many
real, verified bugs as possible (D111, quality first). The current loop stays as it is and stays
the default; both engines run on the same benchmarks so they can be compared.

## Why
Measured (D104): Sonnet and Opus did no better than Haiku in the current loop, so the model isn't
the limit; the harness is: 40 steps, mostly text instead of pixels, one fixed tool per step, no
way to measure with JavaScript or read the page source, no test plan. Deep mode gives a strong
model that freedom and keeps what makes this a product: verification and evidence.

## Settings (the owner's decisions)
- Limits: 400 steps and 60 minutes per run by default, configurable per workspace and per run (a
  run can only lower its workspace's). The same defaults for the evaluation runs.
- Customers: the API key path, each workspace with its own key. No separate cost cap (D111).
- The owner's evaluation: the owner's Claude login, Sonnet 5.5 at effort high by default, Opus
  5.5 optional per run. Paid extra usage is never enabled.
- Screenshots go to the model as JPEG, at most 1280 px wide.
- A usage limit pauses the run: it saves its map, plan, progress and findings, is marked
  "paused: usage limit", and can be resumed later from where it stopped (`worker resume RUN_ID`
  and a dashboard button). Findings so far go through verification as usual.
- Selected with `mode=deep` (API), `--engine deep` (CLI) and the dashboard.

## What deep mode is
- An engine driven by the Claude Agent SDK, with our own tools only (no file, shell or web tools):
  browser actions, screenshots, the accessibility snapshot, visible text, JavaScript in the page,
  the page source and its scripts, console and network evidence, our deterministic checks (axe,
  layout, meta, keyboard probe), and `report_bug`.
- A process the harness enforces: map the app, write a test plan from a generic QA checklist,
  work through it (at 390×844, 768×1024 and 1440×900, looking at screenshots), and review each
  candidate before reporting it. The map, the plan and the progress are saved with the run.
- Verification: interaction bugs by replaying the recorded tool calls (the existing replay and
  pixel check); measurement bugs by re-running the stored snippet or check in a fresh browser at
  the same viewport. What can't be checked either way is kept apart as "unverified".

## PRs (stacked, none merged)
0. `docs-quality-first`: the quality-first principle (D111), the roadmap items after deep mode.
1. `deep-data`: schema (engine, coverage, paused, unverified, workspace limits) and settings.
2. `deep-toolbox`: the tools and their safety; steps recorded so replay can repeat them.
3. `deep-harness`: phases, gates, the checklist, candidates, budgets, a scripted driver.
4. `deep-sdk`: the Agent SDK driver, the locked-down CLI, usage, pausing on a usage limit.
5. `deep-verify`: re-measurement, the model's own replay steps, the unverified path.
6. `deep-run`: wiring into runs, CLI (`run-local --engine deep`, `resume`, `bench --engine deep`),
   export, and an end-to-end test on the demo shop with a fake model at $0.
7. `deep-web`: dashboard (engine choice, coverage panel, unverified section, resume button),
   `/api/v1` and OpenAPI.

## Acceptance
- `npm test` and `npm run lint` pass on every PR; unit tests never call a model.
- The fake-model end-to-end test runs deep mode on the demo shop at $0, with a verified finding,
  an unverified one kept apart, and saved coverage.
- Nothing in deep mode's prompts, checklist or code is specific to one site; a guard test checks
  the prompts and tools against the benchmark apps' names and bug descriptions.

## Evaluation (only after every PR passes and the owner says go; one run at a time, a report
after each)
1. The demo shop, buggy and clean builds.
2. The IT-Tools Roman-numeral and base32 bugs (`docs/REAL_WORLD.md`: IT-1, IT-5).
Scored with the repo's scoring and judge; results in `docs/BENCHMARKS.md` and
`docs/REAL_WORLD.md` next to the current loop's: recall, clean-build false alarms, verified vs
unverified, cost and duration per run.
