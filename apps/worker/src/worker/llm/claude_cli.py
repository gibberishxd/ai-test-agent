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
"""

import json
import re
import subprocess
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from worker.llm.base import Decision, LLMClient, TextResult, ToolCall, ToolSpec, Usage

Runner = Callable[[list[str], str, Path], str]  # (command, stdin, working directory) -> stdout
TIMEOUT_S = 300


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
        raise RuntimeError(f"claude exited with {result.returncode}: {result.stderr[:300]}")
    return result.stdout


class ClaudeCliClient(LLMClient):
    provider = "claude-cli"

    def __init__(
        self,
        agent_model: str = "sonnet",
        cheap_model: str = "haiku",
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
        usage = Usage(model=self.agent_model)
        problem = ""
        for _attempt in range(2):  # the first answer, and one retry with the reason
            text, used = self._call(self.agent_model, system, prompt, image_path)
            usage.input_tokens += used.input_tokens
            usage.output_tokens += used.output_tokens
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
        for folder in (self._temp_dir, image_path.parent if image_path else None):
            if folder is not None:
                outside_repo(folder)
        data = json.loads(self._run(command, prompt, self._temp_dir))
        usage = data.get("usage") or {}
        return str(data.get("result") or ""), Usage(
            model=model,
            input_tokens=usage.get("input_tokens", 0) or 0,
            output_tokens=usage.get("output_tokens", 0) or 0,
            cost_usd=0.0,  # the Pro plan: no per-call charge
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
