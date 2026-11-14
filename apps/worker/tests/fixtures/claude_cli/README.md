# claude-cli JSON fixtures

- `haiku_screenshot.json`: **recorded** 2026-11-15 (run 6, L1) from one real call:
  `claude -p --model claude-haiku-5-5 --output-format json --restricted ...` in a temp folder
  outside the repo, asked to read a 64×32 blue PNG and answer with a tool-call JSON. Session ids
  zeroed, credential expiry removed. Everything else is exactly what the CLI printed.
- `usage_limit.json`: **synthetic**. The shape a usage-limit answer is expected to have
  (`is_error` with "usage limit" text and HTTP 429). Not recorded: that would spend the owner's limit.
- `fallback_credit.json`: **synthetic**. The recorded answer with `usage.fallback_credit` set, as
  when a call is paid from usage credits after the weekly limit.
