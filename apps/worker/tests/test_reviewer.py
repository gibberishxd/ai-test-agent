"""The reviewer tier (run 5, K2): a stronger model decides on flagged steps and final candidates.

The explorer (a cheap model) drives the browser. It is good at reaching states and bad at
judging them (run 4: Gemma explained away 19 of 23 flagged contradictions). The reviewer sees
only the few steps that matter and decides whether each is a bug, and writes the report.
"""

import json

from worker.agent.reviewer import review_candidate, review_mismatch
from worker.llm import FakeClient

PNG = b"\x89PNG fake"


def mismatch(llm, **overrides):
    args = {
        "target_url": "http://shop.test/",
        "action": 'Click button "Save changes"',
        "expected": "'Profile saved'",
        "happened": "nothing on the page changed",
        "flags": ["expected text 'Profile saved' is not on the page"],
        "page_text": "Profile\nDisplay name\nSave changes",
        "screenshot": PNG,
    }
    return review_mismatch(llm, **{**args, **overrides})


def test_a_mismatch_the_reviewer_calls_a_bug_comes_back_with_a_report():
    answer = {
        "bug": True,
        "reason": "Save gives no response",
        "title": "Save changes does nothing",
        "severity": "high",
        "category": "functional",
        "expected": "a confirmation and the new name",
        "actual": "nothing changes",
    }
    llm = FakeClient(texts=[json.dumps(answer)])
    review = mismatch(llm)
    assert review.is_bug and review.report["title"] == "Save changes does nothing"
    assert review.report["severity"] == "high"
    call = llm.calls[0]
    assert call["method"] == "review_screenshot" and call["image"] == PNG
    prompt = call["prompt"]
    assert "'Profile saved'" in prompt and "nothing on the page changed" in prompt
    assert "<page_content>" in prompt  # page text is fenced as untrusted


def test_a_mismatch_the_reviewer_rejects_says_why():
    llm = FakeClient(texts=['{"bug": false, "reason": "the expectation was wrong"}'])
    review = mismatch(llm)
    assert not review.is_bug and review.reason == "the expectation was wrong"
    assert review.usage is not None


def test_an_unclear_answer_on_a_mismatch_is_not_a_bug():
    review = mismatch(FakeClient(texts=["hmm, hard to say"]))
    assert not review.is_bug and "no clear answer" in review.reason


def test_an_invalid_severity_becomes_medium_and_a_missing_title_is_filled():
    llm = FakeClient(texts=['{"bug": true, "reason": "r", "severity": "urgent"}'])
    review = mismatch(llm)
    assert review.report["severity"] == "medium"
    assert review.report["title"]


def test_secrets_are_scrubbed_from_what_the_reviewer_sees():
    llm = FakeClient(texts=['{"bug": false, "reason": "r"}'])
    mismatch(
        llm,
        page_text="Signed in as tester@example.com",
        scrub=lambda text: text.replace("tester@example.com", "[username]"),
    )
    assert "tester@example.com" not in llm.calls[0]["prompt"]


def candidate(llm, **overrides):
    args = {
        "target_url": "http://shop.test/",
        "title": "Cart total ignores quantity",
        "expected": "$24.00",
        "actual": "$12.00",
        "evidence": "Socks × 2, Total $12.00",
        "steps": ['Click button "Add to cart"', 'Type "2" in spinbutton "Quantity"'],
    }
    return review_candidate(llm, **{**args, **overrides})


def test_a_candidate_the_reviewer_keeps_can_be_rewritten():
    answer = {
        "bug": True,
        "reason": "arithmetic is wrong",
        "title": "Cart total doesn't multiply by quantity",
        "severity": "high",
        "category": "functional",
        "expected": "2 × $12.00 = $24.00",
        "actual": "Total: $12.00",
    }
    llm = FakeClient(texts=[json.dumps(answer)])
    review = candidate(llm)
    assert review.is_bug and review.report["expected"] == "2 × $12.00 = $24.00"
    call = llm.calls[0]
    assert call["method"] == "complete" and call["cheap"] is False  # the reviewer's main model
    assert "Cart total ignores quantity" in call["prompt"]
    assert 'Type "2" in spinbutton "Quantity"' in call["prompt"]


def test_a_candidate_the_reviewer_drops_says_why():
    review = candidate(FakeClient(texts=['{"bug": false, "reason": "a design choice"}']))
    assert not review.is_bug and review.reason == "a design choice"


def test_an_unclear_answer_keeps_the_candidate():
    """Dropping a report on a garbled answer would lose bugs; replay still checks it."""
    review = candidate(FakeClient(texts=["no json here"]))
    assert review.is_bug and review.report == {}
