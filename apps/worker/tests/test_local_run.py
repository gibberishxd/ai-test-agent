"""One interactive run against any app on localhost (worker run-local URL), with its own viewport
and artifact folder, and an optional JSON export."""

import json
from pathlib import Path

import pytest

from worker.config import Settings
from worker.db.models import Run, Workspace
from worker.llm import FakeClient, ToolCall
from worker.local_run import (
    LOCAL_WORKSPACE_SLUG,
    local_origin,
    local_settings,
    queue_local_run,
    run_local,
)

# --- which URLs ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "origin"),
    [
        ("http://localhost:5180/", "http://localhost:5180"),
        ("http://localhost:5180", "http://localhost:5180"),
        ("http://127.0.0.1:8080/app/index.html?x=1", "http://127.0.0.1:8080"),
    ],
)
def test_a_local_url_with_a_port_is_accepted(url, origin):
    assert local_origin(url) == origin


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/",
        "http://localhost/",  # no port: be explicit about which app
        "http://localhost.example.com:5180/",
        "http://192.168.1.20:5180/",
        "file:///etc/passwd",
        "localhost:5180",
    ],
)
def test_anything_else_is_refused(url):
    with pytest.raises(ValueError):
        local_origin(url)


# --- settings for the run -----------------------------------------------------------------------


def test_local_settings_need_dev_mode(tmp_path):
    with pytest.raises(ValueError, match="DEV_MODE"):
        local_settings(Settings(_env_file=None), "http://localhost:5180/", tmp_path)


def test_local_settings_allow_only_this_app_and_store_in_the_given_folder(tmp_path):
    base = Settings(_env_file=None, dev_mode=True, local_app_urls="http://localhost:1111")
    settings = local_settings(base, "http://localhost:5180/page", tmp_path / "artifacts")
    assert settings.local_app_urls == "http://localhost:5180"
    assert settings.data_path() == (tmp_path / "artifacts").resolve()
    assert settings.data_path().is_absolute()


# --- queueing -----------------------------------------------------------------------------------


def test_queue_makes_an_interactive_run_with_the_viewport(sessions):
    with sessions() as session:
        first = queue_local_run(session, "http://localhost:5180/", "390x844")
        second = queue_local_run(session, "http://localhost:5180/", None)
        runs = [session.get(Run, first), session.get(Run, second)]
        assert [(r.mode, r.viewport) for r in runs] == [
            ("interactive", "390x844"),
            ("interactive", None),
        ]
        # Both in the one workspace for local runs, created once.
        assert session.query(Workspace).filter_by(slug=LOCAL_WORKSPACE_SLUG).count() == 1
        assert {r.workspace_id for r in runs} == {
            session.query(Workspace).filter_by(slug=LOCAL_WORKSPACE_SLUG).one().id
        }


def test_queue_refuses_a_bad_viewport(sessions):
    with sessions() as session, pytest.raises(ValueError):
        queue_local_run(session, "http://localhost:5180/", "huge")


# --- a whole run --------------------------------------------------------------------------------


def test_a_local_run_keeps_every_artifact_in_its_folder_and_exports(
    sessions, site_url, tmp_path, browser
):
    artifacts = tmp_path / "artifacts"
    export = tmp_path / "results" / "run.json"
    settings = local_settings(
        Settings(_env_file=None, dev_mode=True, max_steps=4, review_pages=0),
        f"{site_url}/form.html",
        artifacts,
    )
    llm = FakeClient(
        decisions=[
            ToolCall("scroll", {"reasoning": "look", "direction": "down"}),
            ToolCall("finish", {"reasoning": "done", "summary": "done"}),
        ],
        default_text='{"duplicates": [], "reproduced": false, "reason": "-"}',
    )
    result = run_local(
        sessions, settings, llm, f"{site_url}/form.html", "390x844", export=export, browser=browser
    )

    assert result["status"] == "done", result
    shots = list(artifacts.rglob("*.png"))
    assert shots, "the run saved no screenshots"
    assert all(Path(p).is_relative_to(artifacts) for p in shots)
    data = json.loads(export.read_text(encoding="utf-8"))
    assert data["run_id"] == result["run_id"]
    assert data["viewport"] == "390x844"
