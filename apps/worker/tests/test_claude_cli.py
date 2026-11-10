"""The claude-cli provider with a stand-in for the `claude` command: no subprocess, no usage."""

import json

from worker.llm import ToolCall, ToolSpec
from worker.llm.claude_cli import ClaudeCliClient

CLICK = ToolSpec(
    "click",
    "Click an element.",
    {
        "type": "object",
        "properties": {"element_id": {"type": "integer"}, "reasoning": {"type": "string"}},
        "required": ["element_id", "reasoning"],
    },
)
FINISH = ToolSpec(
    "finish",
    "End.",
    {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]},
)


class FakeCli:
    """Answers each call with the next scripted result and records the command and input."""

    def __init__(self, *results: str):
        self.results = list(results)
        self.calls = []

    def __call__(self, command: list[str], stdin: str, cwd) -> str:
        self.calls.append({"command": command, "stdin": stdin, "cwd": cwd})
        return json.dumps(
            {
                "type": "result",
                "result": self.results.pop(0),
                "usage": {"input_tokens": 900, "output_tokens": 30},
            }
        )


def test_decide_asks_for_strict_json_and_reads_the_tool_call():
    cli = FakeCli('{"name": "click", "arguments": {"element_id": 4, "reasoning": "open it"}}')
    llm = ClaudeCliClient(run=cli)
    decision = llm.decide("SYSTEM", "OBSERVATION", [CLICK, FINISH])

    assert decision.tool_call == ToolCall("click", {"element_id": 4, "reasoning": "open it"})
    assert decision.usage.cost_usd == 0 and decision.usage.input_tokens == 900
    command = cli.calls[0]["command"]
    assert command[:2] == ["claude", "-p"]
    assert command[command.index("--model") + 1] == "sonnet"
    assert command[command.index("--system-prompt") + 1] == "SYSTEM"
    assert "--no-session-persistence" in command
    stdin = cli.calls[0]["stdin"]
    assert "OBSERVATION" in stdin and '"name": "click"' in stdin and "only one JSON object" in stdin


def test_invalid_json_is_retried_once_with_the_reason():
    cli = FakeCli(
        "I would click the cart.",
        '{"name": "finish", "arguments": {"summary": "done"}}',
    )
    decision = ClaudeCliClient(run=cli).decide("s", "o", [CLICK, FINISH])
    assert decision.tool_call == ToolCall("finish", {"summary": "done"})
    assert "not valid" in cli.calls[1]["stdin"]


def test_a_second_invalid_answer_ends_the_step_with_a_clear_error():
    cli = FakeCli(
        '{"name": "teleport", "arguments": {}}',
        '{"name": "click", "arguments": {"reasoning": "no id"}}',
    )
    decision = ClaudeCliClient(run=cli).decide("s", "o", [CLICK, FINISH])
    assert decision.tool_call is None
    assert "missing element_id" in decision.text
    assert len(cli.calls) == 2


def test_a_screenshot_is_handed_over_as_a_file_it_may_read(tmp_path):
    cli = FakeCli('{"name": "finish", "arguments": {"summary": "x"}}')
    ClaudeCliClient(run=cli, temp_dir=tmp_path).decide("s", "o", [FINISH], image=b"\x89PNG")
    command, stdin = cli.calls[0]["command"], cli.calls[0]["stdin"]
    assert command[command.index("--allowedTools") + 1] == "Read"
    assert str(tmp_path) in command
    path = next(tmp_path.glob("*.png"))
    assert str(path) in stdin
    assert path.read_bytes() == b"\x89PNG"


def test_without_a_screenshot_no_tools_are_allowed():
    cli = FakeCli('{"name": "finish", "arguments": {"summary": "x"}}')
    ClaudeCliClient(run=cli).decide("s", "o", [FINISH])
    assert "--allowedTools" not in cli.calls[0]["command"]


def test_complete_uses_haiku():
    cli = FakeCli('{"match": 5}')
    result = ClaudeCliClient(run=cli).complete("prompt", system="judge")
    assert result.text == '{"match": 5}'
    command = cli.calls[0]["command"]
    assert command[command.index("--model") + 1] == "haiku"


def test_the_cli_runs_outside_the_repo_and_restricted(tmp_path):
    # Started inside the repo, Claude Code would load CLAUDE.md and could read bugs.json:
    # the model must only ever see the page under test.
    calls = []

    def run(command, stdin, cwd):
        calls.append((command, cwd))
        return json.dumps({"result": '{"name": "finish", "arguments": {"summary": "x"}}'})

    ClaudeCliClient(run=run, temp_dir=tmp_path).decide("s", "o", [FINISH])
    command, cwd = calls[0]
    assert cwd == tmp_path
    assert "--restricted" in command


def test_every_call_refuses_a_working_folder_inside_the_repo():
    # Run 3 rule: before every claude-cli call, check it can't reach the repo (bugs.json).
    import pytest

    from worker.config import REPO_ROOT

    cli = FakeCli([json.dumps({"result": '{"name": "finish", "arguments": {"summary": "x"}}'})])
    inside = REPO_ROOT / "apps" / "worker" / "data"
    with pytest.raises(RuntimeError, match="inside the repo"):
        ClaudeCliClient(run=cli, temp_dir=inside).decide("s", "o", [FINISH])
    assert cli.calls == []  # refused before anything ran


def test_every_call_refuses_a_working_folder_that_contains_the_repo(tmp_path):
    import pytest

    from worker.config import REPO_ROOT

    cli = FakeCli([])
    with pytest.raises(RuntimeError, match="inside the repo"):
        ClaudeCliClient(run=cli, temp_dir=REPO_ROOT.parent).complete("hi")
    assert cli.calls == []
