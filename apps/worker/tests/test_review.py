"""Screenshot review with FakeClient: desktop and phone screenshots, no model, no browser."""

import json

from worker.llm import FakeClient
from worker.report import PageResult
from worker.review import review_screenshots


class MemoryStorage:
    def __init__(self, files):
        self.files = files

    def save(self, key, data):
        self.files[key] = data
        return key

    def load(self, key):
        return self.files[key]


ISSUE = json.dumps([{"title": "Title runs out of its box", "severity": "medium"}])
PAGE = PageResult(
    url="http://site.test/p/6", status=200, screenshot="d.png", mobile_screenshot="m.png"
)
STORAGE = MemoryStorage({"d.png": b"desktop-png", "m.png": b"mobile-png"})


def test_each_page_is_reviewed_at_desktop_and_phone_width():
    llm = FakeClient(texts=["[]", ISSUE])
    result = review_screenshots([PAGE], llm, STORAGE, limit=6, budget_usd=1.0)

    assert [c["image"] for c in llm.calls] == [b"desktop-png", b"mobile-png"]
    assert "375" in llm.calls[1]["prompt"] and "375" not in llm.calls[0]["prompt"]
    [bug] = result.bugs
    assert bug.category == "layout"
    assert bug.screenshot == "m.png"
    assert bug.evidence["viewport"] == "mobile"  # replay must look at the same screen size
    assert "375" in bug.repro_steps[1]
    assert len(result.usages) == 2


def test_desktop_findings_are_visual_and_carry_no_viewport():
    llm = FakeClient(texts=[ISSUE, "[]"])
    [bug] = review_screenshots([PAGE], llm, STORAGE, limit=6, budget_usd=1.0).bugs
    assert bug.category == "visual" and bug.screenshot == "d.png"
    assert "viewport" not in bug.evidence


def test_a_page_without_a_phone_screenshot_is_reviewed_once():
    page = PageResult(url="http://site.test/", status=200, screenshot="d.png")
    llm = FakeClient(texts=["[]"])
    review_screenshots([page], llm, STORAGE, limit=6, budget_usd=1.0)
    assert len(llm.calls) == 1
