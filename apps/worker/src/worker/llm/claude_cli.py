"""Claude through the `claude` command line (Claude Code), with the owner's Pro login.

For the owner's local testing only: no API key, so no API bill, but every call uses the same
Pro limit as an interactive Claude Code session. `make_client` refuses to build it unless
DEV_MODE is on and nothing says production, and the workspace UI never offers it.

The CLI has no tool-calling interface for our tools, so the prompt lists the tools as JSON
schemas and asks for one JSON object `{"name": ..., "arguments": {...}}`. The answer is
validated against the schema; an invalid answer is retried once with the reason, then the
step ends with a clear error (the loop counts it as a step with no action).

The CLI runs in a temporary folder outside the repo with --restricted: started inside the repo
it would load CLAUDE.md and could read the demo apps' bugs.json, which would spoil the
benchmark. A screenshot is written to that folder for the Read tool; without one, no tools.

Run 6 (L1) made these runs measurable: models are pinned by full ID (CLAUDE_CLI_MODEL,
CLAUDE_CLI_CHEAP_MODEL), every call records the model the CLI reports and all four token
types, and an API-equivalent cost estimate is computed from them with llm/pricing.py (the
charged cost stays $0). A usage-limit answer, or a call paid from usage credits, latches: no
claude-cli client in this process calls the CLI again (the owner's credits are never drained
by a loop).
"""

import json
import logging
import re
import subprocess
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from worker.llm.base import (
    Decision,
    LLMClient,
    TextResult,
    ToolCall,
    ToolSpec,
    Usage,
    UsageLimitReached,
)
from worker.llm.pricing import cost_usd

log = logging.getLogger(__name__)

Runner = Callable[[list[str], str, Path], str]  # (command, stdin, working directory) -> stdout
TIMEOUT_S = 300

# A full model ID ("claude-sonnet-5-5", "claude-sonnet-4-5-20250929"), not an alias ("sonnet").
PINNED_ID = re.compile(r"^claude-[a-z]+(-\d+)+$")
# How the CLI says the plan's limit is reached (checked on errors only, case-insensitive).
LIMIT_TEXT = re.compile(r"usage limit|hit your limit|limit reached|rate.?limit|weekly limit", re.I)

_limit_message: str | None = None  # set once a call reports a usage limit: see _check_latch


class CliFailed(RuntimeError):
    """The `claude` command exited with an error (its stderr and stdout are in the message)."""

    def __init__(self, code: int, output: str):
        super().__init__(f"claude exited with {code}: {output[:300]}")
        self.output = output


def run_cli(command: list[str], stdin: str, cwd: Path) -> str:
    result = subprocess.run(
        command,
        input=stdin,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_S,
        check=False,
    )
    if result.returncode != 0:
        raise CliFailed(result.returncode, f"{result.stderr} {result.stdout}".strip())
    return result.stdout


def is_pinned_model_id(model: str) -> bool:
    return bool(PINNED_ID.match(model or ""))


def limit_reached() -> str | None:
    """Why claude-cli calls stopped in this process, or None while they may still run."""
    return _limit_message


def reset_limit_latch() -> None:
    """For tests only: a real process never un-latches."""
    global _limit_message
    _limit_message = None


def _latch(message: str) -> UsageLimitReached:
    global _limit_message
    _limit_message = _limit_message or message
    log.error("claude-cli stopped: %s", message)
    return UsageLimitReached(message)


def usage_from_cli(data: dict, requested: str) -> Usage:
    """Tokens, the model the CLI reports and the API-equivalent cost of one CLI answer.

    `modelUsage` (one entry per model the call used) is preferred: it names the model exactly
    and lets each be priced at its own rate. Without it, `usage` and the requested model.
    """
    per_model = data.get("modelUsage") or {}
    if not per_model:
        u = data.get("usage") or {}
        per_model = {
            requested: {
                "inputTokens": u.get("input_tokens"),
                "outputTokens": u.get("output_tokens"),
                "cacheReadInputTokens": u.get("cache_read_input_tokens"),
                "cacheCreationInputTokens": u.get("cache_creation_input_tokens"),
                "cacheCreationEphemeral1hInputTokens": (u.get("cache_creation") or {}).get(
                    "ephemeral_1h_input_tokens"
                ),
            }
        }
    total = Usage(model="+".join(m.get("canonicalModel") or name for name, m in _items(per_model)))
    for name, m in _items(per_model):
        part = Usage(
            model=m.get("canonicalModel") or name,
            input_tokens=int(m.get("inputTokens") or 0),
            output_tokens=int(m.get("outputTokens") or 0),
            cache_read_tokens=int(m.get("cacheReadInputTokens") or 0),
            cache_write_tokens=int(m.get("cacheCreationInputTokens") or 0),
            cache_write_1h_tokens=int(m.get("cacheCreationEphemeral1hInputTokens") or 0),
        )
        total.input_tokens += part.input_tokens
        total.output_tokens += part.output_tokens
        total.cache_read_tokens += part.cache_read_tokens
        total.cache_write_tokens += part.cache_write_tokens
        total.cache_write_1h_tokens += part.cache_write_1h_tokens
        total.estimated_cost_usd += cost_usd(part.model, part)
    reported = data.get("total_cost_usd")
    if isinstance(reported, int | float) and reported > 0:
        if abs(reported - total.estimated_cost_usd) > 0.01 * reported:
            # The CLI prices its own calls at list price: a gap means pricing.py is out of date.
            log.warning(
                "claude-cli estimate $%.6f differs from the CLI's own $%.6f (%s): check pricing.py",
                total.estimated_cost_usd,
                reported,
                total.model,
            )
    return total  # cost_usd stays 0: the Pro plan charges nothing per call


def _items(per_model: dict) -> list[tuple[str, dict]]:
    return [(name, m) for name, m in per_model.items() if isinstance(m, dict)]


def _check_answer(data: dict) -> None:
    """Raise on an error answer: UsageLimitReached for a limit or credits, else RuntimeError."""
    usage = data.get("usage") or {}
    if usage.get("fallback_credit"):
        raise _latch("the call was paid from usage credits (the weekly limit is used up)")
    if data.get("is_error"):
        text = f"{data.get('result') or ''} {data.get('api_error_status') or ''}"
        if LIMIT_TEXT.search(text) or data.get("api_error_status") == 429:
            raise _latch(f"usage limit: {text.strip()[:200]}")
        raise RuntimeError(f"claude-cli error: {text.strip()[:300]}")


class ClaudeCliClient(LLMClient):
    provider = "claude-cli"

    def __init__(
        self,
        agent_model: str = "claude-sonnet-5-5",
        cheap_model: str = "claude-haiku-5-5",
        run: Runner = run_cli,
        temp_dir: Path | None = None,
    ):
        self.agent_model = agent_model
        self.cheap_model = cheap_model
        self._run = run
        self._temp_dir = temp_dir or Path(tempfile.mkdtemp(prefix="claude-cli-"))

    def decide(
        self, system: str, observation: str, tools: list[ToolSpec], image: bytes | None = None
    ) -> Decision:
        prompt = observation + "\n\n" + _tool_instructions(tools)
        image_path = self._write_image(image) if image else None
        if image_path:
            prompt += f"\n\nA screenshot of the current page is at {image_path}. Read it first."
        usage = Usage(model="")  # filled from the CLI's answers
        problem = ""
        for _attempt in range(2):  # the first answer, and one retry with the reason
            text, used, denied = self._call_with_denials(
                self.agent_model, system, prompt, image_path
            )
            usage = _add(usage, used)
            if denied:
                # The model tried to call a tool natively, was refused by the CLI and may have
                # concluded it has no tools (run 3, H7). Don't take that answer; correct it once.
                problem = f"you tried to call {', '.join(denied)} as a native tool"
                prompt += native_tool_correction(denied)
                continue
            call, problem = parse_tool_answer(text, tools)
            if call:
                return Decision(tool_call=call, text=text, usage=usage)
            prompt += (
                f"\n\nYour previous answer was not valid: {problem}. "
                "Answer with only the JSON object."
            )
        return Decision(
            tool_call=None, text=f"error: invalid tool answer twice ({problem})", usage=usage
        )

    def review_screenshot(self, prompt: str, image: bytes, system: str | None = None) -> TextResult:
        path = self._write_image(image)
        text, usage = self._call(
            self.agent_model, system, f"{prompt}\n\nThe screenshot is at {path}.", path
        )
        return TextResult(text, usage)

    def complete(self, prompt: str, system: str | None = None, cheap: bool = True) -> TextResult:
        text, usage = self._call(self.cheap_model if cheap else self.agent_model, system, prompt)
        return TextResult(text, usage)

    def _write_image(self, image: bytes) -> Path:
        path = self._temp_dir / f"screen-{uuid.uuid4().hex[:8]}.png"
        path.write_bytes(image)
        return path

    def _call(
        self, model: str, system: str | None, prompt: str, image_path: Path | None = None
    ) -> tuple[str, Usage]:
        text, usage, _ = self._call_with_denials(model, system, prompt, image_path)
        return text, usage

    def _call_with_denials(
        self, model: str, system: str | None, prompt: str, image_path: Path | None = None
    ) -> tuple[str, Usage, list[str]]:
        """The answer, its usage, and the tools the CLI refused (native tool-call attempts;
        reading the screenshot with Read is allowed and isn't one)."""
        command = [
            "claude",
            "-p",
            "--model",
            model,
            "--output-format",
            "json",
            "--no-session-persistence",
            "--strict-mcp-config",
            # No shell or code tools, and file tools only in the working directory: the temp
            # folder, outside the repo, so this project's files (bugs.json!) stay out of reach.
            "--restricted",
        ]
        if system:
            command += ["--system-prompt", system]
        if image_path:
            command += ["--allowedTools", "Read", "--add-dir", str(image_path.parent)]
        if _limit_message:
            raise UsageLimitReached(f"claude-cli stopped earlier: {_limit_message}")
        for folder in (self._temp_dir, image_path.parent if image_path else None):
            if folder is not None:
                outside_repo(folder)
        try:
            out = self._run(command, prompt, self._temp_dir)
        except CliFailed as error:
            if LIMIT_TEXT.search(error.output):
                raise _latch(f"usage limit: {error.output.strip()[:200]}") from error
            raise
        data = json.loads(out)
        _check_answer(data)
        denied = list(
            dict.fromkeys(
                str(d.get("tool_name") or "?")
                for d in data.get("permission_denials") or []
                if isinstance(d, dict)
            )
        )
        return str(data.get("result") or ""), usage_from_cli(data, requested=model), denied


def _add(total: Usage, more: Usage) -> Usage:
    """Two calls' usage as one (a decision retried once); the reported model is kept."""
    return Usage(
        model=total.model or more.model,
        input_tokens=total.input_tokens + more.input_tokens,
        output_tokens=total.output_tokens + more.output_tokens,
        cache_read_tokens=total.cache_read_tokens + more.cache_read_tokens,
        cache_write_tokens=total.cache_write_tokens + more.cache_write_tokens,
        cache_write_1h_tokens=total.cache_write_1h_tokens + more.cache_write_1h_tokens,
        cost_usd=total.cost_usd + more.cost_usd,
        estimated_cost_usd=total.estimated_cost_usd + more.estimated_cost_usd,
    )


def native_tool_correction(denied: list[str]) -> str:
    return (
        f"\n\nYou tried to call {', '.join(denied)} as a native tool. That is not how tools work "
        "here, and it does not mean you have no tools: you do have every tool listed above. "
        'Choose one by answering with only the JSON object {"name": ..., "arguments": {...}}, '
        "and keep testing."
    )


def outside_repo(folder: Path) -> None:
    """Refuse to let the CLI work in, or read, a folder that is or contains this repo.

    Checked before every call: the CLI's file tools reach its working folder and --add-dir,
    and the repo holds the demo apps' bug lists, which would spoil the benchmark.
    """
    from worker.config import REPO_ROOT

    folder, repo = folder.resolve(), REPO_ROOT.resolve()
    if folder == repo or repo in folder.parents or folder in repo.parents:
        raise RuntimeError(f"claude-cli refused: {folder} is inside the repo or contains it")


def _tool_instructions(tools: list[ToolSpec]) -> str:
    listing = json.dumps(
        [{"name": t.name, "description": t.description, "parameters": t.parameters} for t in tools],
        indent=1,
    )
    return (
        f"TOOLS (call exactly one):\n{listing}\n\n"
        'Answer with only one JSON object, nothing else: {"name": "<tool name>", '
        '"arguments": {...}} where arguments match that tool\'s parameters.'
    )


def parse_tool_answer(text: str, tools: list[ToolSpec]) -> tuple[ToolCall | None, str]:
    """The tool call in `text`, or None and why it isn't a valid one."""
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None, "no JSON object in the answer"
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as error:
        return None, f"invalid JSON ({error.msg})"
    if not isinstance(data, dict):
        return None, "the JSON is not an object"
    by_name = {t.name: t for t in tools}
    name, arguments = data.get("name"), data.get("arguments")
    if name not in by_name:
        return None, f"unknown tool {name!r}"
    if not isinstance(arguments, dict):
        return None, "arguments must be an object"
    missing = _missing(by_name[name].parameters, arguments)
    if missing:
        return None, "missing " + ", ".join(missing)
    return ToolCall(name, arguments), ""


def _missing(schema: dict[str, Any], arguments: dict) -> list[str]:
    required = [k for k in schema.get("required", []) if k != "reasoning"]
    return [key for key in required if key not in arguments]
