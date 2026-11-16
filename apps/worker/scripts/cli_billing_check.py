"""One claude-cli Haiku call, to show it is billed to the Pro plan and not the API (run 8, N0).

The API key from .env is put into this process's environment on purpose (as a worker that also
runs LLM_PROVIDER=claude would have it), then one call goes through ClaudeCliClient's real path
(outside-the-repo check, stripped environment). The CLI's stream-json `init` event says which
credential it used: "apiKeySource": "none" means the owner's login (Pro plan). The key is never
printed; only whether it was set in the parent and what the CLI reports.

  cd apps/worker && uv run python scripts/cli_billing_check.py
"""

import json
import os
from pathlib import Path

from worker.config import get_settings
from worker.llm.claude_cli import ClaudeCliClient, run_cli

seen: dict = {}


def stream_runner(command: list[str], stdin: str, cwd: Path) -> str:
    command = [c if c != "json" else "stream-json" for c in command] + ["--verbose"]
    out = run_cli(command, stdin, cwd)
    result = {}
    for line in out.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "system" and event.get("subtype") == "init":
            seen["apiKeySource"] = event.get("apiKeySource")
            seen["model"] = event.get("model")
        if event.get("type") == "result":
            result = event
    return json.dumps(result)


def main() -> None:
    key = get_settings().anthropic_api_key.get_secret_value()
    os.environ["ANTHROPIC_API_KEY"] = key  # the parent has it; the CLI must not
    print(f"parent has ANTHROPIC_API_KEY: {bool(os.environ.get('ANTHROPIC_API_KEY'))}")
    client = ClaudeCliClient("claude-haiku-5-5", "claude-haiku-5-5", run=stream_runner)
    answer = client.complete("Reply with the single word: ok", cheap=True)
    u = answer.usage
    print(f"CLI apiKeySource: {seen.get('apiKeySource')!r} (none = Pro login, not the API key)")
    print(f"CLI model: {seen.get('model')!r}; reported: {u.model!r}")
    print(f"answer: {answer.text.strip()[:40]!r}")
    print(f"provider: {client.provider}; charged cost_usd: {u.cost_usd}")
    print(
        f"tokens in/out/cache read/write: {u.input_tokens}/{u.output_tokens}/"
        f"{u.cache_read_tokens}/{u.cache_write_tokens}; API-equivalent ${u.estimated_cost_usd:.5f}"
    )


if __name__ == "__main__":
    main()
