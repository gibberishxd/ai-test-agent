"""The `claude` subprocess never sees an Anthropic API key (run 8, N0).

With ANTHROPIC_API_KEY (or ANTHROPIC_AUTH_TOKEN) in its environment, `claude -p` bills the API
key's credits instead of the owner's Pro plan. The worker may have the key (LLM_PROVIDER=claude
runs need it), so run_cli strips both before starting the CLI.
"""

from pathlib import Path

from worker.llm.claude_cli import cli_environment, run_cli

FAKE_KEY = "test-not-a-real-key"


def test_the_cli_environment_drops_both_anthropic_credentials(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", FAKE_KEY)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    env = cli_environment()

    assert "ANTHROPIC_API_KEY" not in env
    assert "ANTHROPIC_AUTH_TOKEN" not in env
    assert env["PATH"] == "/usr/bin:/bin"  # everything else is kept (the CLI needs HOME, PATH)


def test_a_real_subprocess_started_by_run_cli_has_no_key(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", FAKE_KEY)

    out = run_cli(["/usr/bin/env"], "", tmp_path)

    assert "ANTHROPIC_API_KEY=" not in out
    assert "ANTHROPIC_AUTH_TOKEN=" not in out
    assert FAKE_KEY not in out
    assert "PATH=" in out


def test_no_tracked_file_holds_a_real_looking_anthropic_key():
    """Real keys are about 100 characters; the test fixtures are short fakes (sk-ant-api03-...).
    Only file names are reported, never the match."""
    import subprocess

    from worker.config import REPO_ROOT

    # CI's container checks the repo out as another user; git then refuses with "dubious
    # ownership" unless the folder is marked safe (only for this one read-only command).
    found = subprocess.run(
        ["git", "-c", "safe.directory=*", "grep", "-lE", "sk-ant-[A-Za-z0-9_-]{40,}"] + ["--", "."],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert found.returncode in (0, 1), found.stderr  # 1 = no match
    assert found.stdout.split() == []
