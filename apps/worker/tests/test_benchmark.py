from types import SimpleNamespace

import pytest

from worker.benchmark import (
    MatchDecision,
    PlantedBug,
    candidates_for,
    load_planted,
    match_report,
    score,
)
from worker.llm import FakeClient

PLANTED = [
    PlantedBug(1, "/products/3", "JS error on Desk Lamp", "TypeError when opening product 3"),
    PlantedBug(2, "/profile", "Profile API 500", "GET /api/profile returns 500"),
    PlantedBug(5, "/cart", "Cart total ignores quantity", "2 mugs show $12 total"),
    PlantedBug(7, "/cart", "Discount applies twice", "double click applies SAVE10 twice"),
]


def report(title, page, actual=""):
    return SimpleNamespace(
        title=title, page_url=f"http://localhost:5173{page}", expected="", actual=actual
    )


def decision(run, matched):
    return MatchDecision(
        run_id=run, report="r", page="/", candidates=[], matched=matched, reason=""
    )


def test_bugs_json_has_twelve_planted_bugs():
    planted = load_planted()
    assert [b.id for b in planted] == list(range(1, 13))


def test_candidates_are_narrowed_by_page():
    assert [b.id for b in candidates_for("http://localhost:5173/cart", PLANTED)] == [5, 7]


def test_unknown_page_considers_every_planted_bug():
    assert len(candidates_for("http://localhost:5173/checkout", PLANTED)) == len(PLANTED)


def test_match_uses_the_cheap_model_and_records_the_decision():
    llm = FakeClient(texts=['{"match": 5, "reason": "same wrong total"}'])
    result = match_report(llm, "run-1", report("Total wrong for 2 mugs", "/cart"), PLANTED)
    assert result.matched == 5
    assert result.candidates == [5, 7]
    assert result.reason == "same wrong total"
    assert llm.calls[0]["cheap"] is True


def test_match_outside_the_candidates_is_rejected():
    llm = FakeClient(texts=['{"match": 1, "reason": "?"}'])  # bug 1 isn't on /cart
    assert match_report(llm, "r", report("x", "/cart"), PLANTED).matched is None


def test_unclear_answer_is_no_match():
    llm = FakeClient(texts=["I think it's bug five"])
    assert match_report(llm, "r", report("x", "/cart"), PLANTED).matched is None


def test_scores():
    buggy = {
        "a": [decision("a", 1), decision("a", 2), decision("a", None)],  # 2 found, 1 false report
        "b": [decision("b", 1), decision("b", 1)],  # 1 found (a duplicate still counts as real)
    }
    scores = score(
        buggy,
        clean_reports={"c": 3},
        planted=PLANTED,
        costs=[0.2, 0.4, 0.3],
        durations=[60, 120, 90],
        provider="fake",
        model="m",
        git_commit="abc",
    )
    assert scores.recall == pytest.approx(((2 / 4) + (1 / 4)) / 2)
    assert scores.precision == pytest.approx(4 / 5)
    assert scores.false_alarms == 3
    assert scores.avg_cost_usd == pytest.approx(0.3)
    assert scores.per_bug[1]["found_runs"] == 2
    assert scores.per_bug[5]["found_runs"] == 0


def test_scores_with_no_reports_are_zero_not_an_error():
    scores = score({"a": []}, {}, PLANTED, [], [], "fake", "m", "abc")
    assert scores.recall == 0 and scores.precision == 0 and scores.false_alarms == 0


@pytest.mark.parametrize("answer", ['{"match": "5"}', '{"match": 5.0}', '{"match": " 5 "}'])
def test_match_accepts_the_id_as_a_string_or_float(answer):
    # A local model answered "match": "2" while its reason said "matches known bug 2".
    llm = FakeClient(texts=[answer])
    assert match_report(llm, "r", report("Total wrong", "/cart"), PLANTED).matched == 5
