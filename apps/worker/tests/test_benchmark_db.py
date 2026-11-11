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
