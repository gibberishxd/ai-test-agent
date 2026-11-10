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
