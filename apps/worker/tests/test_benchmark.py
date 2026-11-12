from types import SimpleNamespace

import pytest

from worker.benchmark import (
    HOLDOUT_BUGS_JSON,
    MatchDecision,
    PlantedBug,
    candidates_for,
    judge_name,
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
# Bug 9 lives on "/", but its $NaN price also shows up in the cart.
WITH_NAN = [*PLANTED, PlantedBug(9, "/", "Wool Socks price is $NaN", "decimal comma in price")]


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


def test_no_match_on_the_page_widens_to_every_planted_bug():
    llm = FakeClient(
        texts=[
            '{"match": null, "reason": "not about quantity or discounts"}',
            '{"match": 9, "reason": "the same NaN price, seen in the cart"}',
        ]
    )
    result = match_report(llm, "r", report("Cart total shows $NaN", "/cart"), WITH_NAN)
    assert result.matched == 9
    assert result.candidates == [1, 2, 5, 7, 9]
    assert len(llm.calls) == 2
    assert "Wool Socks" in llm.calls[1]["prompt"]


def test_match_on_the_page_needs_only_one_call():
    llm = FakeClient(texts=['{"match": 5, "reason": "same wrong total"}'])
    match_report(llm, "r", report("Total wrong for 2 mugs", "/cart"), PLANTED)
    assert len(llm.calls) == 1


def test_no_second_call_when_every_bug_was_already_a_candidate():
    llm = FakeClient(texts=['{"match": null, "reason": "none of these"}'])
    result = match_report(llm, "r", report("Odd spacing", "/checkout"), PLANTED)
    assert result.matched is None
    assert len(llm.calls) == 1


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


def test_judge_name_is_the_provider_and_the_model_that_answers_cheap_calls():
    llm = SimpleNamespace(provider="claude", agent_model="claude-sonnet-5-5", cheap_model="haiku")
    assert judge_name(llm) == "claude/haiku"


def test_scores_record_the_judge():
    scores = score({}, {}, PLANTED, [], [], "ollama", "qwen", "abc", judge="ollama/gemma4:12b")
    assert scores.judge == "ollama/gemma4:12b"


# --- honest numbers: AI-only recall, holdout, judge, rescore commit ----------------------------

MIXED = [
    PlantedBug(1, "/", "Console error", "", detection="deterministic"),
    PlantedBug(2, "/", "Broken link", "", detection="deterministic"),
    PlantedBug(5, "/cart", "Total ignores quantity", "", detection="agent"),
    PlantedBug(6, "/checkout", "Invalid email accepted", "", detection="agent"),
]


def test_ai_recall_counts_only_the_bugs_that_need_judgement():
    # Run a: both deterministic bugs and one of the two AI bugs. Run b: deterministic only.
    buggy = {"a": [decision("a", 1), decision("a", 2), decision("a", 5)], "b": [decision("b", 1)]}
    scores = score(buggy, {}, MIXED, [], [], "fake", "m", "abc")
    assert scores.recall == pytest.approx((3 / 4 + 1 / 4) / 2)
    assert scores.ai_recall == pytest.approx((1 / 2 + 0 / 2) / 2)


def test_load_planted_reads_how_each_bug_can_be_detected():
    shop = load_planted()
    assert {b.detection for b in shop} == {"deterministic", "agent"}
    assert [b.id for b in shop if b.detection == "deterministic"] == [1, 2, 3, 4]


def test_holdout_has_its_own_planted_bugs_of_the_same_kinds():
    holdout = load_planted(HOLDOUT_BUGS_JSON)
    assert len(holdout) == 6
    assert {b.detection for b in holdout} == {"deterministic", "agent"}
    shop_titles = {b.title for b in load_planted()}
    assert not shop_titles & {b.title for b in holdout}


def test_per_bug_results_say_how_each_bug_is_detected():
    scores = score({"a": [decision("a", 5)]}, {}, MIXED, [], [], "fake", "m", "abc")
    assert scores.per_bug[5] == {
        "title": "Total ignores quantity",
        "found_runs": 1,
        "detection": "agent",
    }


# --- Run 3, H2: what verification throws away ----------------------------------------------


def staged(run, matched, stage="verified", failure_kind=None):
    return MatchDecision(
        run_id=run,
        report="r",
        page="/",
        candidates=[],
        matched=matched,
        reason="",
        stage=stage,
        failure_kind=failure_kind,
    )


FUNNEL_RUNS = {
    "a": [
        staged("a", 1),  # verified, matches bug 1
        staged("a", 5, "could_not_replay", "element_not_found"),  # correct but discarded
        staged("a", None, "judge_said_no"),  # discarded, and rightly so
        staged("a", 1, "duplicate"),  # merged into the first report
    ],
    "b": [
        staged("b", 7, "judge_said_no"),  # correct but discarded
        staged("b", 7, "verified"),  # ...but another report of bug 7 survived
        staged("b", None, "verified"),  # verified, matches nothing: lowers precision
    ],
}


def test_recall_and_precision_count_only_reports_that_survived_verification():
    scores = score(FUNNEL_RUNS, {}, PLANTED, [], [], "fake", "m", "abc")
    assert scores.recall == pytest.approx((1 / 4 + 1 / 4) / 2)  # a: {1}, b: {7}
    assert scores.precision == pytest.approx(2 / 3)  # 3 surviving reports, 2 matched


def test_recall_before_verification_counts_every_report_except_duplicates():
    scores = score(FUNNEL_RUNS, {}, PLANTED, [], [], "fake", "m", "abc")
    assert scores.recall_before == pytest.approx((2 / 4 + 1 / 4) / 2)  # a: {1, 5}, b: {7}


def test_the_verification_funnel_counts_each_stage_and_why_reports_were_discarded():
    funnel = score(FUNNEL_RUNS, {}, PLANTED, [], [], "fake", "m", "abc").verification
    assert funnel["reported"] == 7
    assert funnel["verified"] == 3
    assert funnel["duplicates"] == 1
    assert funnel["discarded_at_replay"] == 3
    assert funnel["discard_reasons"] == {"element_not_found": 1, "judge_said_no": 2}


def test_correct_but_discarded_counts_discarded_reports_that_match_a_planted_bug():
    scores = score(FUNNEL_RUNS, {}, PLANTED, [], [], "fake", "m", "abc")
    assert scores.correct_but_discarded == 2  # bug 5 in run a, bug 7 in run b
    # Bug 5 in run a was lost entirely; bug 7 in run b survived through another report.
    assert scores.verification["bugs_lost"] == 1


def test_false_alarms_before_and_after_verification():
    scores = score({}, {"clean": 1}, PLANTED, [], [], "fake", "m", "abc", clean_before={"clean": 4})
    assert scores.false_alarms == 1.0
    assert scores.false_alarms_before == 4.0


def test_false_alarms_before_verification_default_to_the_ones_after():
    scores = score({}, {"clean": 2}, PLANTED, [], [], "fake", "m", "abc")
    assert scores.false_alarms_before == 2.0


def test_stage_of_a_bug_follows_how_verification_ended():
    from worker.benchmark import stage_of

    def bug(status, reason=None, evidence=None, duplicate=False):
        return SimpleNamespace(
            status=status,
            dismiss_reason=reason,
            evidence=evidence or {},
            duplicate_of_id="x" if duplicate else None,
        )

    assert stage_of(bug("confirmed")) == ("verified", None)
    assert stage_of(bug("candidate")) == ("verified", None)  # never checked: still reported
    assert stage_of(bug("dismissed", "replay: works fine")) == ("judge_said_no", None)
    failed = {"replay_failure": {"kind": "timeout"}}
    assert stage_of(bug("dismissed", "could not replay: x", failed)) == (
        "could_not_replay",
        "timeout",
    )
    # Runs from before failure kinds were stored.
    assert stage_of(bug("dismissed", "could not replay: x")) == ("could_not_replay", "unknown")
    assert stage_of(bug("dismissed", "duplicate of: y", duplicate=True)) == ("duplicate", None)


def test_printed_scores_show_what_verification_threw_away(capsys):
    from worker.benchmark import print_scores

    print_scores(score(FUNNEL_RUNS, {"c": 0}, PLANTED, [], [], "fake", "m", "abc"))
    out = capsys.readouterr().out
    assert "reported 7 → verified 3 (duplicates 1, discarded at replay 3)" in out
    assert "correct but discarded  2" in out
    assert "element_not_found 1, judge_said_no 2" in out
    assert "recall before verification" in out
    assert "false alarms before verification" in out
