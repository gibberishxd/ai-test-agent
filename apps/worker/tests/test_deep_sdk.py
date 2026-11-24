"""Deep mode's Agent SDK driver, without a model: a fake CLI speaks the SDK's control protocol
(it asks for our tools the way the real CLI does) and plays scripted turns. No API call, no
login, $0. Also: the locked-down options, the credential wrapper, auth rules, usage limits."""

import asyncio
import json
import os
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from claude_agent_sdk import AssistantMessage, RateLimitEvent, ResultMessage
from claude_agent_sdk.types import RateLimitInfo

from worker.config import REPO_ROOT, Settings
from worker.deep.checklist import AREAS, VIEWPORTS
from worker.deep.harness import Harness, HarnessConfig, MemoryRecorder
from worker.deep.sdk_driver import (
    SERVER,
    DeepAuthError,
    SdkConfig,
    SdkDriver,
    check_auth,
    cli_wrapper,
    limit_reason,
    options_for,
    turn_usage,
)
from worker.deep.toolbox import Toolbox, ToolboxConfig
from worker.llm import claude_cli
from worker.safety.network import NetworkGuard


class FakeCli:
    """Stands in for the Claude Code CLI: answers the SDK's control requests and, for each user
    turn, calls our MCP tools in order, then ends the turn with a result message."""

    def __init__(self, turns, before=None, result_extra=None):
        self.turns = list(turns)
        self.before = before or {}  # turn number → messages sent before its tool calls
        self.result_extra = result_extra or {}
        self.tool_results: list[dict] = []
        self.interrupted = False
        self._out: asyncio.Queue | None = None
        self._waiting: dict[str, asyncio.Future] = {}
        self._n = 0
        self._turn = 0
        self._mcp_ready = False

    # Transport interface
    async def connect(self):
        self._out = asyncio.Queue()

    def is_ready(self):
        return True

    async def end_input(self):
        pass

    async def close(self):
        await self._out.put(None)

    async def read_messages(self):
        while (message := await self._out.get()) is not None:
            yield message

    async def write(self, data: str):
        for line in data.splitlines():
            if line.strip():
                await self._receive(json.loads(line))

    async def _receive(self, message: dict):
        if message["type"] == "control_request":
            if message["request"]["subtype"] == "interrupt":
                self.interrupted = True
            await self._out.put(
                {
                    "type": "control_response",
                    "response": {
                        "subtype": "success",
                        "request_id": message["request_id"],
                        "response": {},
                    },
                }
            )
        elif message["type"] == "control_response":
            future = self._waiting.pop(message["response"]["request_id"], None)
            if future:
                future.set_result(message["response"])
        elif message["type"] == "user":
            asyncio.get_running_loop().create_task(self._play_turn())

    async def _mcp(self, method: str, params: dict, notify=False) -> dict | None:
        self._n += 1
        request_id = f"cli_{self._n}"
        body = {"jsonrpc": "2.0", "method": method, "params": params}
        if not notify:
            body["id"] = self._n
        future = asyncio.get_running_loop().create_future()
        self._waiting[request_id] = future
        await self._out.put(
            {
                "type": "control_request",
                "request_id": request_id,
                "request": {"subtype": "mcp_message", "server_name": SERVER, "message": body},
            }
        )
        response = await future
        return response.get("response", {}).get("mcp_response")

    async def _play_turn(self):
        self._turn += 1
        if not self._mcp_ready:
            await self._mcp(
                "initialize",
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "fake", "version": "1"},
                },
            )
            await self._mcp("notifications/initialized", {}, notify=True)
            self._mcp_ready = True
        for message in self.before.get(self._turn, []):
            await self._out.put(message)
        calls = self.turns.pop(0) if self.turns else []
        for name, args in calls:
            if self.interrupted:
                break
            reply = await self._mcp("tools/call", {"name": name, "arguments": args})
            self.tool_results.append(reply)
            await self._out.put(_assistant(f"called {name}"))
        await self._out.put(
            {
                "type": "result",
                "subtype": "success",
                "duration_ms": 1,
                "duration_api_ms": 1,
                "is_error": False,
                "num_turns": 1,
                "session_id": "fake-session",
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 100,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
                **self.result_extra,
            }
        )


def _assistant(text: str) -> dict:
    return {
        "type": "assistant",
        "message": {
            "id": f"m-{text}",
            "model": "claude-sonnet-5-5",
            "content": [{"type": "text", "text": text}],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        },
        "session_id": "fake-session",
    }


MAP = {
    "pages": [{"url": "/deep.html", "purpose": "counter"}],
    "flows": [{"name": "count", "description": "add one"}],
    "summary": "tiny",
}


def full_plan() -> dict:
    items = [
        {"id": f"{a.key}-1", "area": a.key, "description": "x"} for a in AREAS if a.key != "layout"
    ]
    items += [
        {"id": f"layout-{v}", "area": "layout", "viewport": v, "description": "x"}
        for v in VIEWPORTS
    ]
    return {"items": items}


@pytest.fixture
def workdir(tmp_path_factory):
    # Outside the repo, like the real per-run folder.
    return tmp_path_factory.mktemp("deep-sdk")


@pytest.fixture
def harness(context, site_url):
    guard = NetworkGuard(
        allowed_local={("127.0.0.1", urlsplit(site_url).port)}, target_url=f"{site_url}/"
    )
    page = context.new_page()
    toolbox = Toolbox(page, guard, ToolboxConfig(target_url=f"{site_url}/deep.html"))
    toolbox.start()
    recorder = MemoryRecorder()
    return Harness(toolbox, HarnessConfig(max_steps=100, max_seconds=120), recorder), recorder


def driver(workdir, cli, auth="api"):
    config = SdkConfig(
        model="claude-sonnet-5-5", effort="high", auth=auth, workdir=workdir, api_key="sk-test"
    )
    return SdkDriver(config, transport_factory=lambda: cli)


# --- end to end through the SDK, with a fake CLI ------------------------------------------


def test_the_sdk_calls_our_tools_through_the_harness_and_finishes(harness, workdir):
    harness_, recorder = harness
    plan = full_plan()
    screenshots = []
    for v in VIEWPORTS:
        w, h = (int(n) for n in v.split("x"))
        screenshots += [("set_viewport", {"width": w, "height": h}), ("screenshot", {})]
    ticks = [("tick", {"item_id": i["id"], "status": "done", "note": "ok"}) for i in plan["items"]]
    cli = FakeCli(
        [
            [("snapshot", {}), ("save_map", MAP)],
            [("save_plan", plan)],
            screenshots + ticks,
            [("finish", {"summary": "done"})],
        ]
    )
    result = driver(workdir, cli).run(harness_)
    assert result.stop_reason == "finished", result
    assert recorder.coverage["phase"] == "done"
    # A screenshot reaches the model as an image block.
    images = [
        r for r in cli.tool_results if any(c.get("type") == "image" for c in r["result"]["content"])
    ]
    assert len(images) == 3
    # Tokens of every turn are counted and priced (API path: charged).
    assert harness_.usage.input_tokens == 4000 and harness_.usage.cost_usd > 0


def test_a_rejected_rate_limit_pauses_the_run(harness, workdir):
    harness_, recorder = harness
    rejected = {
        "type": "rate_limit_event",
        "uuid": "u",
        "session_id": "s",
        "rate_limit_info": {"status": "rejected", "rateLimitType": "seven_day"},
    }
    cli = FakeCli([[("save_map", MAP)], [("save_plan", full_plan())]], before={2: [rejected]})
    result = driver(workdir, cli, auth="api").run(harness_)
    assert result.stop_reason == "paused: usage limit"
    assert harness_.paused and recorder.coverage["phase"] == "plan"


def test_the_login_path_latches_so_nothing_else_uses_the_plan(harness, workdir, monkeypatch):
    claude_cli.reset_limit_latch()
    monkeypatch.setattr("worker.deep.sdk_driver.cli_wrapper", lambda folder: folder / "x.sh")
    harness_, _ = harness
    rejected = {
        "type": "rate_limit_event",
        "uuid": "u",
        "session_id": "s",
        "rate_limit_info": {"status": "rejected"},
    }
    cli = FakeCli([[("snapshot", {})]], before={1: [rejected]})
    driver(workdir, cli, auth="cli").run(harness_)
    assert claude_cli.limit_reached()
    claude_cli.reset_limit_latch()


def test_when_the_harness_stops_mid_turn_the_model_is_interrupted(context, site_url, workdir):
    guard = NetworkGuard(
        allowed_local={("127.0.0.1", urlsplit(site_url).port)}, target_url=f"{site_url}/"
    )
    page = context.new_page()
    toolbox = Toolbox(page, guard, ToolboxConfig(target_url=f"{site_url}/deep.html"))
    toolbox.start()
    harness_ = Harness(toolbox, HarnessConfig(max_steps=2, max_seconds=120), MemoryRecorder())
    cli = FakeCli([[("snapshot", {})] * 6])
    result = driver(workdir, cli).run(harness_)
    assert result.stop_reason.startswith("step budget")
    assert cli.interrupted
    assert len(cli.tool_results) <= 4


# --- the locked-down CLI -------------------------------------------------------------------


def test_options_lock_the_cli_down_to_our_tools(workdir):
    config = SdkConfig(
        model="claude-opus-5-5", effort="high", auth="api", workdir=workdir, api_key="sk-x"
    )
    options = options_for(config, server={"type": "sdk"})
    assert options.tools == []
    assert options.strict_mcp_config is True
    assert options.setting_sources == []
    assert options.permission_mode == "dontAsk"
    assert set(options.mcp_servers) == {SERVER}
    assert all(name.startswith(f"mcp__{SERVER}__") for name in options.allowed_tools)
    assert (options.model, options.effort) == ("claude-opus-5-5", "high")
    assert options.env["ANTHROPIC_API_KEY"] == "sk-x" and options.cli_path is None


def test_on_the_login_path_the_key_never_reaches_the_cli(workdir):
    config = SdkConfig(
        model="claude-sonnet-5-5", effort="high", auth="cli", workdir=workdir, api_key="sk-x"
    )
    options = options_for(config, server={"type": "sdk"})
    assert "ANTHROPIC_API_KEY" not in options.env
    assert options.cli_path and Path(options.cli_path).exists()


def test_the_wrapper_removes_the_api_credentials(workdir):
    wrapper = cli_wrapper(workdir, target=Path("/usr/bin/env"))  # print the environment
    env = {
        **os.environ,
        "ANTHROPIC_API_KEY": "sk-secret",
        "ANTHROPIC_AUTH_TOKEN": "tok",
        "KEEP": "1",
    }
    out = subprocess.run([str(wrapper)], env=env, capture_output=True, text=True, check=True).stdout
    assert "sk-secret" not in out and "ANTHROPIC_AUTH_TOKEN" not in out and "KEEP=1" in out


def test_the_cli_never_works_inside_the_repo():
    config = SdkConfig(
        model="claude-sonnet-5-5", effort="high", auth="api", workdir=REPO_ROOT, api_key="k"
    )
    with pytest.raises(RuntimeError):
        options_for(config, server={})


def test_auth_rules():
    dev, prod = Settings(_env_file=None, dev_mode=True), Settings(_env_file=None, dev_mode=False)
    check_auth(dev, "cli", None)
    with pytest.raises(DeepAuthError):
        check_auth(prod, "cli", None)
    with pytest.raises(DeepAuthError):
        check_auth(dev, "api", None)
    check_auth(prod, "api", "sk-x")


# --- usage limits and cost -----------------------------------------------------------------


def info(**fields):
    return RateLimitEvent(rate_limit_info=RateLimitInfo(**fields), uuid="u", session_id="s")


def result(**fields):
    base = {
        "subtype": "success",
        "duration_ms": 1,
        "duration_api_ms": 1,
        "is_error": False,
        "num_turns": 1,
        "session_id": "s",
    }
    return ResultMessage(**{**base, **fields})


@pytest.mark.parametrize(
    "message",
    [
        info(status="rejected", rate_limit_type="five_hour"),
        info(status="allowed", rate_limit_type="overage"),
        info(status="allowed", raw={"isUsingOverage": True}),
        AssistantMessage(content=[], model="m", error="billing_error"),
        AssistantMessage(content=[], model="m", error="rate_limit"),
        result(is_error=True, api_error_status=429),
        result(is_error=True, result="Credit balance is too low"),
        result(usage={"fallback_credit": True}),
    ],
)
def test_limit_and_billing_signals_pause(message):
    assert limit_reason(message)


@pytest.mark.parametrize(
    "message",
    [
        info(status="allowed", rate_limit_type="five_hour"),
        info(status="allowed_warning", rate_limit_type="seven_day", utilization=0.9),
        AssistantMessage(content=[], model="m"),
        result(),
        result(is_error=True, api_error_status=500, errors=["overloaded"]),
    ],
)
def test_other_messages_dont(message):
    assert limit_reason(message) is None


def test_turn_usage_is_priced_and_charged_only_on_the_api():
    message = result(usage={"input_tokens": 1_000_000, "output_tokens": 0})
    api = turn_usage(message, "claude-sonnet-5-5", "api")
    login = turn_usage(message, "claude-sonnet-5-5", "cli")
    assert api.cost_usd == pytest.approx(2.0) and api.estimated_cost_usd == pytest.approx(2.0)
    assert login.cost_usd == 0 and login.estimated_cost_usd == pytest.approx(2.0)


class GoneSession(FakeCli):
    """The CLI can't find the session it was asked to resume."""

    async def connect(self):
        raise RuntimeError("No conversation found with session ID: old")


def test_a_lost_session_on_resume_starts_a_fresh_one(harness, workdir):
    harness_, _ = harness
    transports = [GoneSession([]), FakeCli([[("snapshot", {}), ("save_map", MAP)]])]
    config = SdkConfig(
        model="claude-sonnet-5-5",
        effort="high",
        auth="api",
        workdir=workdir,
        api_key="k",
        resume_session="old",
    )
    sdk = SdkDriver(config, transport_factory=lambda: transports.pop(0))
    sdk.run(harness_)
    assert harness_.map is not None  # the fresh session went on with the run
    assert sdk.session_id == "fake-session"
