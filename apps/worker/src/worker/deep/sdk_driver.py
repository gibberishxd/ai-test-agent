"""Deep mode's real driver: Claude through the Claude Agent SDK (`claude-agent-sdk`, pinned).

The SDK runs the Claude Code CLI as a subprocess and gives it our tools as an in-process MCP
server ("qa"). The CLI is locked down to those tools only:
- `tools=[]` removes every built-in tool (no file, shell or web access), `strict_mcp_config`
  loads no other MCP server (not the user's, not claude.ai connectors), `setting_sources=[]`
  loads no settings or CLAUDE.md, and `permission_mode="dontAsk"` refuses anything not on the
  allow list without asking anyone;
- it runs in a per-run folder outside the repo (checked), so even a file tool, if one appeared,
  couldn't reach the benchmark's answer keys.

Authentication (DEEP_AUTH):
- `api`: the workspace's (or worker's) API key, passed to the CLI in its environment only.
- `cli`: this machine's Claude login, for the owner's local evaluation (DEV_MODE only, never in
  production). The SDK always passes the worker's whole environment to the CLI and can't remove
  a variable, so the CLI is started through a small wrapper script that unsets
  ANTHROPIC_API_KEY and ANTHROPIC_AUTH_TOKEN first: the login is used, never the key.

Threads (a new idea here): the SDK is async and calls our tools from its own event loop, while
Playwright's sync API only works on the thread that created the browser. So the SDK runs in a
background thread, and every harness call (tools, prompts, usage, saving) is handed to the main
thread through a queue and waited for. The harness and the browser only ever run on the main
thread; the database writes behind the recorder too.

Usage limits: a rejected rate limit, a switch to paid overage ("extra usage"), a billing or
rate-limit error, or a result paid from usage credits pauses the run at once (the harness keeps
everything), and no later claude-cli call in this process is made. Paid extra usage is never
used: the first sign of it pauses.

Cost: each turn's tokens come from the turn's result message and are priced with our own
pricing.py (the SDK's `total_cost_usd` is also only a client-side estimate). On the API path
that is the charge; on the login path the charge is $0 and the price is the API-equivalent
estimate, as for claude-cli.
"""

import asyncio
import base64
import os
import queue
import re
import tempfile
import threading
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import claude_agent_sdk
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    RateLimitEvent,
    ResultMessage,
    ToolAnnotations,
    create_sdk_mcp_server,
    tool,
)

from worker.config import Settings
from worker.deep.harness import Harness
from worker.deep.prompt import SYSTEM_PROMPT
from worker.deep.scripted import DriverResult, TurnDriver
from worker.deep.tools import ALL_TOOLS
from worker.llm import claude_cli
from worker.llm.base import ToolSpec, Usage, UsageLimitReached
from worker.llm.claude_cli import API_CREDENTIALS, LIMIT_TEXT, outside_repo
from worker.llm.pricing import cost_usd

SERVER = "qa"
MAX_RESULT_CHARS = 60_000  # keep tool results inline (the CLI would otherwise save big ones to
# a file the model has no tool to read)
BILLING_TEXT = re.compile(r"credit balance|billing|usage credits|extra usage|overage", re.I)
TOOL_NAMING = (
    f"\n\nYour tools are named mcp__{SERVER}__<tool> (for example mcp__{SERVER}__snapshot); "
    "they are the only tools you have."
)


class DeepAuthError(Exception):
    """Deep mode can't authenticate as configured (said before anything runs)."""


@dataclass(frozen=True)
class SdkConfig:
    model: str
    effort: str
    auth: str  # "api" or "cli"
    workdir: Path  # outside the repo; the CLI's working folder (and where it keeps the session)
    api_key: str | None = None
    resume_session: str | None = None


def check_auth(settings: Settings, auth: str, api_key: str | None) -> None:
    """Refuse a configuration that would use the wrong credential, before any call."""
    if auth == "cli":
        if not settings.dev_mode:
            raise DeepAuthError("DEEP_AUTH=cli only runs with DEV_MODE=true (local evaluation)")
        if "production" in (os.environ.get("NODE_ENV", ""), os.environ.get("ENV", "")):
            raise DeepAuthError("DEEP_AUTH=cli never runs in production")
    elif auth == "api":
        if not api_key:
            raise DeepAuthError("deep mode with DEEP_AUTH=api needs an API key")
    else:
        raise DeepAuthError(f"unknown DEEP_AUTH {auth!r}")


def bundled_cli() -> Path:
    return Path(claude_agent_sdk.__file__).parent / "_bundled" / "claude"


def cli_wrapper(workdir: Path, target: Path | None = None) -> Path:
    """A script that starts the CLI without the API credentials in its environment."""
    path = workdir / "claude-without-api-key.sh"
    unset = " ".join(API_CREDENTIALS)
    path.write_text(f'#!/bin/sh\nunset {unset}\nexec "{target or bundled_cli()}" "$@"\n')
    path.chmod(0o700)
    return path


def run_workdir(run_id: str) -> Path:
    """The CLI's folder for one run: in the system temp folder, outside the repo (checked),
    the same across a pause and resume on this machine (the session lives there)."""
    folder = Path(tempfile.gettempdir()) / "ata-deep" / run_id
    folder.mkdir(parents=True, exist_ok=True)
    outside_repo(folder)
    return folder


def options_for(config: SdkConfig, server: Any) -> ClaudeAgentOptions:
    env = {"ENABLE_TOOL_SEARCH": "false"}  # every tool's schema up front: there are few
    cli_path = None
    if config.auth == "api":
        env["ANTHROPIC_API_KEY"] = config.api_key or ""
    else:
        cli_path = str(cli_wrapper(config.workdir))
    outside_repo(config.workdir)
    return ClaudeAgentOptions(
        model=config.model,
        effort=config.effort,
        system_prompt=SYSTEM_PROMPT + TOOL_NAMING,
        tools=[],
        mcp_servers={SERVER: server},
        strict_mcp_config=True,
        allowed_tools=[f"mcp__{SERVER}__{spec.name}" for spec in ALL_TOOLS],
        permission_mode="dontAsk",
        setting_sources=[],
        cwd=str(config.workdir),
        cli_path=cli_path,
        env=env,
        resume=config.resume_session,
    )


def limit_reason(message: Any) -> str | None:
    """Why this message means the plan's limit (or paid usage) is reached, or None."""
    if isinstance(message, RateLimitEvent):
        info = message.rate_limit_info
        if info.status == "rejected":
            return f"usage limit reached ({info.rate_limit_type or 'plan'})"
        if info.rate_limit_type == "overage" or info.raw.get("isUsingOverage"):
            return "the plan's limit is used up; paid extra usage would be next"
        return None
    if isinstance(message, AssistantMessage):
        if message.error in ("billing_error", "rate_limit"):
            return message.error.replace("_", " ")
        if (message.usage or {}).get("fallback_credit"):
            return "the call was paid from usage credits"
        return None
    if isinstance(message, ResultMessage):
        if (message.usage or {}).get("fallback_credit"):
            return "the call was paid from usage credits"
        if not message.is_error:
            return None
        text = " ".join([*(message.errors or []), message.result or ""])
        if message.api_error_status in (402, 429) or LIMIT_TEXT.search(text):
            return f"usage limit: {text.strip()[:200] or message.api_error_status}"
        if BILLING_TEXT.search(text):
            return f"billing: {text.strip()[:200]}"
    return None


def turn_usage(result: ResultMessage, model: str, auth: str) -> Usage:
    """One turn's tokens and price (the turn's own usage, priced with pricing.py)."""
    raw = result.usage or {}
    usage = Usage(
        model=model,
        input_tokens=int(raw.get("input_tokens") or 0),
        output_tokens=int(raw.get("output_tokens") or 0),
        cache_read_tokens=int(raw.get("cache_read_input_tokens") or 0),
        cache_write_tokens=int(raw.get("cache_creation_input_tokens") or 0),
    )
    price = cost_usd(model, usage)
    usage.estimated_cost_usd = price
    usage.cost_usd = price if auth == "api" else 0.0
    return usage


class MainThread:
    """Runs functions on the main thread for code on other threads, which wait for the result."""

    def __init__(self):
        self._jobs: queue.Queue = queue.Queue()

    def call(self, fn: Callable[[], Any]) -> Any:
        future: Future = Future()
        self._jobs.put((fn, future))
        return future.result()

    def serve_until(self, done: threading.Event) -> None:
        while not done.is_set():
            try:
                fn, future = self._jobs.get(timeout=0.05)
            except queue.Empty:
                continue
            try:
                future.set_result(fn())
            except BaseException as error:  # handed back to the waiting thread
                future.set_exception(error)


class SdkDriver(TurnDriver):
    def __init__(self, config: SdkConfig, transport_factory: Callable[[], Any] | None = None):
        self.config = config
        self.transport_factory = transport_factory  # tests: a fake CLI
        self.session_id: str | None = config.resume_session
        self._stop_now = False

    def run(self, harness: Harness) -> DriverResult:
        result = DriverResult(stop_reason="")
        if self.config.auth == "cli" and claude_cli.limit_reached():
            harness.pause(f"claude-cli stopped earlier: {claude_cli.limit_reached()}")
            result.stop_reason = harness.stop_reason
            return result
        error = self._run_once(harness, result)
        if (
            error is not None
            and not isinstance(error, UsageLimitReached)
            and self.config.resume_session
            and result.turns == 0
        ):
            # Resuming a session this machine no longer has (a reboot cleared the temp folder):
            # start a fresh one; the harness's saved coverage carries the run on.
            self.config = replace(self.config, resume_session=None)
            self.session_id = None
            error = self._run_once(harness, result)
        if isinstance(error, UsageLimitReached):
            if self.config.auth == "cli":
                claude_cli.latch(str(error))
            harness.pause(str(error))
        elif error is not None:
            harness.stop(f"the model session failed: {_first_line(error)}")
        result.stop_reason = harness.stop_reason
        return result

    def _run_once(self, harness: Harness, result: DriverResult) -> BaseException | None:
        """One SDK session in a background thread, serving harness calls on this thread."""
        main, done, failure = MainThread(), threading.Event(), {}

        def session_thread() -> None:
            try:
                asyncio.run(self._session(harness, main, result))
            except BaseException as error:
                failure["error"] = error
            finally:
                done.set()

        thread = threading.Thread(target=session_thread, name="deep-sdk", daemon=True)
        thread.start()
        main.serve_until(done)
        thread.join()
        return failure.get("error")

    async def _session(self, harness: Harness, main: MainThread, result: DriverResult) -> None:
        async def on_main(fn: Callable[[], Any]) -> Any:
            return await asyncio.to_thread(main.call, fn)

        server = create_sdk_mcp_server(
            name=SERVER,
            version="1.0.0",
            tools=[self._tool(spec, harness, on_main) for spec in ALL_TOOLS],
        )
        options = options_for(self.config, server)
        transport = self.transport_factory() if self.transport_factory else None
        async with ClaudeSDKClient(options=options, transport=transport) as client:
            while (prompt := await on_main(harness.next_prompt)) is not None:
                result.prompts.append(prompt)
                result.turns += 1
                await client.query(prompt)
                interrupted = False
                async for message in client.receive_response():
                    reason = limit_reason(message)
                    if reason:
                        raise UsageLimitReached(reason)
                    if isinstance(message, AssistantMessage | ResultMessage) and message.session_id:
                        self.session_id = message.session_id
                    if isinstance(message, ResultMessage):
                        usage = turn_usage(message, self.config.model, self.config.auth)
                        await on_main(lambda usage=usage: harness.add_usage(usage))
                        if message.is_error and not self._stop_now:
                            text = " ".join(message.errors or []) or message.result or ""
                            await on_main(
                                lambda text=text: harness.stop(f"model error: {text[:200]}")
                            )
                    elif self._stop_now and not interrupted:
                        interrupted = True
                        await client.interrupt()
                if self._stop_now:
                    break

    def _tool(self, spec: ToolSpec, harness: Harness, on_main) -> Any:
        async def handler(args: dict[str, Any]) -> dict[str, Any]:
            result = await on_main(lambda: harness.call(spec.name, args))
            if harness.stop_reason:
                self._stop_now = True  # the run is over: interrupt the model's turn
            content: list[dict[str, Any]] = [{"type": "text", "text": result.text}]
            if result.image:
                content.append(
                    {
                        "type": "image",
                        "data": base64.b64encode(result.image).decode("ascii"),
                        "mimeType": "image/jpeg",
                    }
                )
            return {"content": content, "is_error": result.is_error}

        annotations = ToolAnnotations(maxResultSizeChars=MAX_RESULT_CHARS)
        return tool(spec.name, spec.description, spec.parameters, annotations=annotations)(handler)


def _first_line(error: BaseException) -> str:
    text = str(error).strip()
    return (text.splitlines()[0] if text else type(error).__name__)[:300]
