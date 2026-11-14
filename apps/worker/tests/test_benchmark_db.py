"""Saving and rescoring benchmark results, against the test database."""

from worker.benchmark import BenchmarkScores, save_scores
from worker.db.models import BenchmarkResult
from worker.llm import FakeClient
from worker.main import rescore_latest


def scores(**fields) -> BenchmarkScores:
    base = dict(
        provider="ollama",
        model="gemma4:12b",
        git_commit="abc1234",
        runs_buggy=3,
        recall=0.42,
        precision=1.0,
        false_alarms=0.0,
        avg_cost_usd=0.0,
        avg_duration_s=500.0,
        ai_recall=0.125,
        judge="ollama/gemma4:12b",
    )
    return BenchmarkScores(**{**base, **fields})


def test_saved_result_has_ai_recall_holdout_and_judge(sessions):
    holdout = scores(runs_buggy=2, recall=0.5, ai_recall=0.25, precision=0.8, false_alarms=1.0)
    with sessions() as session:
        saved = save_scores(session, scores(holdout=holdout), {"buggy": [], "clean": []})
        row = session.get(BenchmarkResult, saved.id)
        assert (row.ai_recall, row.judge, row.rescore_commit) == (0.125, "ollama/gemma4:12b", None)
        assert (row.holdout_recall, row.holdout_ai_recall) == (0.5, 0.25)
        assert (row.holdout_precision, row.holdout_false_alarms, row.holdout_runs_buggy) == (
            0.8,
            1.0,
            2,
        )


def test_result_without_holdout_leaves_the_holdout_columns_empty(sessions):
    with sessions() as session:
        row = save_scores(session, scores(), {"buggy": [], "clean": []})
        assert row.holdout_recall is None and row.holdout_runs_buggy is None


def test_rescore_keeps_the_original_commit_and_records_its_own(sessions, monkeypatch):
    monkeypatch.setattr("worker.main.git_commit", lambda: "def5678")
    with sessions() as session:
        save_scores(session, scores(git_commit="abc1234"), {"buggy": [], "clean": []})
    rescore_latest(sessions, FakeClient())
    with sessions() as session:
        latest = session.query(BenchmarkResult).order_by(BenchmarkResult.created_at.desc()).first()
        assert (latest.git_commit, latest.rescore_commit) == ("abc1234", "def5678")


# --- Run 3, H2 -------------------------------------------------------------------------------


def test_saved_result_keeps_what_verification_did_for_shop_and_holdout(sessions):
    funnel = {"reported": 5, "verified": 3, "discard_reasons": {"timeout": 1}}
    holdout = scores(correct_but_discarded=1, verification={"reported": 2})
    with sessions() as session:
        row = save_scores(
            session,
            scores(
                recall_before=0.5,
                ai_recall_before=0.25,
                false_alarms_before=2.0,
                correct_but_discarded=2,
                verification=funnel,
                holdout=holdout,
            ),
            {"buggy": [], "clean": []},
        )
        saved = session.get(BenchmarkResult, row.id).details["verification"]
    assert saved == {
        **funnel,
        "recall_before": 0.5,
        "ai_recall_before": 0.25,
        "false_alarms_before": 2.0,
        "correct_but_discarded": 2,
    }
    assert row.details["holdout"]["verification"]["correct_but_discarded"] == 1


def test_scoring_matches_discarded_reports_too_and_records_their_stage(sessions, workspace):
    from worker.benchmark import PlantedBug
    from worker.db.models import Bug, Run
    from worker.main import _score_set

    def bug(run, title, status="confirmed", **fields):
        return Bug(
            run_id=run.id,
            title=title,
            severity="medium",
            category="functional",
            page_url="http://localhost:5173/cart",
            source="agent",
            status=status,
            **fields,
        )

    with sessions() as session:
        buggy, clean = (Run(workspace_id=workspace.id, target_url="http://x/") for _ in range(2))
        session.add_all([buggy, clean])
        session.flush()
        kept = bug(buggy, "Total is wrong")
        session.add(kept)
        session.flush()
        session.add_all(
            [
                bug(
                    buggy,
                    "Save does nothing",
                    "dismissed",
                    dismiss_reason="could not replay: step 2 (type): no textbox",
                    evidence={"replay_failure": {"kind": "element_not_found"}},
                ),
                bug(
                    buggy,
                    "Total wrong again",
                    "dismissed",
                    dismiss_reason="duplicate of: Total is wrong",
                    duplicate_of_id=kept.id,
                ),
                bug(clean, "Clean run report", "dismissed", dismiss_reason="replay: fine"),
            ]
        )
        session.commit()
        planted = [
            PlantedBug(5, "/cart", "Cart total", "ignores quantity"),
            PlantedBug(8, "/cart", "Save", "does nothing"),
        ]
        judge = FakeClient(texts=['{"match": 5}', '{"match": 8}'])
        result = _score_set(session, judge, [str(buggy.id)], [str(clean.id)], planted, "abc")

    stages = {d.report: (d.stage, d.failure_kind, d.matched) for d in result.decisions}
    assert stages == {
        "Total is wrong": ("verified", None, 5),
        "Save does nothing": ("could_not_replay", "element_not_found", 8),
        "Total wrong again": ("duplicate", None, None),  # duplicates aren't sent to the judge
    }
    assert len(judge.calls) == 2
    assert result.correct_but_discarded == 1
    assert (result.false_alarms, result.false_alarms_before) == (0.0, 1.0)


def test_a_benchmark_is_labelled_with_the_commit_its_runs_were_made_on(
    sessions, monkeypatch, tmp_path
):
    # Run 2 and run 3 committed new code while a 2-hour benchmark ran; the result was labelled
    # with HEAD at scoring time, i.e. code the runs never used.
    from worker.config import Settings
    from worker.main import run_benchmark

    head = {"commit": "made0on"}
    monkeypatch.setattr("worker.main.git_commit", lambda: head["commit"])

    def execute(*_):  # someone commits new code while the runs are being made
        head["commit"] = "later00"

    settings = Settings(_env_file=None, demo_url="http://x/", clean_demo_url="http://y/")
    run_benchmark(settings, FakeClient(), FakeClient(), sessions, execute, 1, "passive", 0)
    with sessions() as session:
        latest = session.query(BenchmarkResult).order_by(BenchmarkResult.created_at.desc()).first()
        assert latest.git_commit == "made0on"


def test_holdout_first_queues_the_holdout_before_the_shop(sessions, monkeypatch):
    # Run 4, J1: a change is judged on the holdout first, so its runs must come first; if the
    # holdout drops, the shop runs can be stopped before they use hours of local compute.
    from worker.config import Settings
    from worker.main import run_benchmark

    monkeypatch.setattr("worker.main.git_commit", lambda: "abc1234")
    order = []

    def execute(_session, run, *_):
        order.append(run.target_url)

    settings = Settings(
        _env_file=None,
        demo_url="http://shop/",
        clean_demo_url="http://shop-clean/",
        demo2_url="http://holdout/",
        clean_demo2_url="http://holdout-clean/",
    )
    run_benchmark(
        settings, FakeClient(), FakeClient(), sessions, execute, 1, "passive", 1, holdout_first=True
    )
    assert order == [
        "http://holdout/",
        "http://holdout-clean/",
        "http://shop/",
        "http://shop-clean/",
    ]


def test_the_shop_benchmark_runs_signed_in_with_the_demo_account(sessions, monkeypatch):
    # Run 4, J2/J7 (owner's question 3, decided without owner: option a): the shop is tested
    # the way customers use the product, with a saved sign-in; the holdout app has no login.
    import base64
    import os

    from worker.config import Settings
    from worker.db.models import LoginSetup
    from worker.main import run_benchmark
    from worker.secret_box import decrypt_secret

    monkeypatch.setattr("worker.main.git_commit", lambda: "abc1234")
    key = os.urandom(32)
    settings = Settings(
        _env_file=None,
        demo_url="http://shop:5173/",
        clean_demo_url="http://shop:5174/",
        demo2_url="http://holdout:5175/",
        clean_demo2_url="http://holdout:5176/",
        model_keys_secret=base64.b64encode(key).decode(),
    )
    run_benchmark(settings, FakeClient(), FakeClient(), sessions, lambda *_: None, 1, "passive", 1)
    with sessions() as session:
        setups = {s.origin: s for s in session.query(LoginSetup).all()}
        assert set(setups) == {"http://shop:5173", "http://shop:5174"}
        shop = setups["http://shop:5173"]
        assert (shop.login_url, shop.username) == ("http://shop:5173/login", "demo@example.com")
        assert (
            decrypt_secret(shop.password_ciphertext, str(shop.workspace_id), key) == "password123"
        )
    run_benchmark(settings, FakeClient(), FakeClient(), sessions, lambda *_: None, 1, "passive", 0)
    with sessions() as session:
        assert session.query(LoginSetup).count() == 2  # saved once, not again per benchmark


# --- Run 6, L1 ---------------------------------------------------------------------------------


def test_saved_result_has_the_estimated_costs(sessions):
    with sessions() as session:
        row = save_scores(
            session,
            scores(avg_estimated_cost_usd=0.3, estimated_cost_per_verified_bug=0.2),
            {"buggy": [], "clean": []},
        )
        assert (row.avg_estimated_cost_usd, row.estimated_cost_per_verified_bug) == (0.3, 0.2)


def _stub_settings(**fields):
    from worker.config import Settings

    return Settings(
        _env_file=None, demo_url="http://shop/", clean_demo_url="http://shop-clean/", **fields
    )


def test_a_usage_limit_stops_the_benchmark_and_records_what_finished(sessions, monkeypatch):
    # Run 6 rule: a usage-limit message stops the benchmark at once, no retry, and what
    # finished is recorded (kept out of the leaderboard as incomplete).
    from worker.db.models import Run
    from worker.llm import UsageLimitReached
    from worker.llm.claude_cli import _latch as latch
    from worker.llm.claude_cli import reset_limit_latch
    from worker.main import run_benchmark

    monkeypatch.setattr("worker.main.git_commit", lambda: "abc1234")
    started = []

    def execute(_session, run, *_):
        started.append(run.target_url)
        if len(started) == 2:
            raise latch("usage limit: Claude AI usage limit reached")

    try:
        run_benchmark(_stub_settings(), FakeClient(), FakeClient(), sessions, execute, 3, "passive")
    finally:
        reset_limit_latch()
    assert len(started) == 2  # the third buggy run and the clean run never started
    with sessions() as session:
        statuses = sorted(r.status for r in session.query(Run))
        assert statuses == ["done", "failed", "stopped", "stopped"]
        latest = session.query(BenchmarkResult).order_by(BenchmarkResult.created_at.desc()).first()
        assert "usage limit" in latest.details["invalid"]
        assert latest.details["incomplete"]["finished"] == 1
    assert UsageLimitReached  # imported for clarity of what latch raises


def test_the_estimated_cost_cap_stops_the_benchmark(sessions, monkeypatch):
    from worker.db.models import Run
    from worker.main import run_benchmark

    monkeypatch.setattr("worker.main.git_commit", lambda: "abc1234")

    def execute(_session, run, *_):
        run.estimated_cost_usd = 0.6  # each run: $0.60 at API prices

    run_benchmark(
        _stub_settings(bench_max_cost_usd=1.0),
        FakeClient(),
        FakeClient(),
        sessions,
        execute,
        3,
        "passive",
    )
    with sessions() as session:
        statuses = sorted(r.status for r in session.query(Run))
        assert statuses == ["done", "done", "stopped", "stopped"]  # $1.20 ≥ $1.00 after two
        latest = session.query(BenchmarkResult).order_by(BenchmarkResult.created_at.desc()).first()
        assert "cost cap" in latest.details["invalid"]


def test_a_benchmark_records_the_models_its_calls_reported(sessions, monkeypatch):
    from worker.db.models import Step
    from worker.main import run_benchmark

    monkeypatch.setattr("worker.main.git_commit", lambda: "abc1234")

    def execute(session, run, *_):
        session.add(Step(run_id=run.id, index=0, action="click", model="claude-haiku-5-5"))
        session.add(Step(run_id=run.id, index=1, action="visit"))  # no model call
        session.commit()

    run_benchmark(_stub_settings(), FakeClient(), FakeClient(), sessions, execute, 1, "passive")
    with sessions() as session:
        latest = session.query(BenchmarkResult).order_by(BenchmarkResult.created_at.desc()).first()
        assert latest.details["reported_models"] == ["claude-haiku-5-5"]
        assert "invalid" not in latest.details
