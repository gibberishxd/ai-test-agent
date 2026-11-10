"""Replay verification and dedup, with FakeClient answers and a real browser."""

import json

from worker.llm import FakeClient
from worker.verify import ReplayStep, find_duplicates, parse_json_object, replay, verify_bug

NAME = {"role": "textbox", "name": "Name"}
SAVE = {"role": "button", "name": "Save"}


def test_replay_repeats_steps_by_role_and_name(context, site_url):
    page = context.new_page()
    replay(
        page,
        f"{site_url}/form.html",
        [ReplayStep("type", {"text": "Ada"}, NAME), ReplayStep("click", {}, SAVE)],
    )
    assert page.locator("#status").inner_text() == "Saved: Ada"


def test_bug_confirmed_when_the_model_sees_it(context, site_url):
    llm = FakeClient(texts=[json.dumps({"reproduced": True, "reason": "status is wrong"})])
    verdict = verify_bug(
        context,
        llm,
        f"{site_url}/form.html",
        [ReplayStep("click", {}, SAVE)],
        "Save shows nothing",
        "Saved: name",
        "empty",
    )
    assert verdict.reproduced is True
    prompt = llm.calls[0]["prompt"]
    assert "Save shows nothing" in prompt and "<page_content>" in prompt
    assert llm.calls[0]["image"].startswith(b"\x89PNG")


def test_bug_dismissed_when_the_model_doesnt_see_it(context, site_url):
    llm = FakeClient(texts=['{"reproduced": false, "reason": "works fine"}'])
    verdict = verify_bug(context, llm, f"{site_url}/form.html", [], "x", None, None)
    assert verdict.reproduced is False
    assert verdict.reason == "works fine"


def test_unclear_answer_counts_as_not_reproduced(context, site_url):
    verdict = verify_bug(
        context, FakeClient(texts=["maybe?"]), f"{site_url}/form.html", [], "x", None, None
    )
    assert verdict.reproduced is False


def test_steps_that_cant_be_replayed_dismiss_the_bug(context, site_url):
    missing = ReplayStep("click", {}, {"role": "button", "name": "Does not exist"})
    llm = FakeClient(texts=['{"reproduced": true, "reason": "x"}'])
    verdict = verify_bug(context, llm, f"{site_url}/form.html", [missing], "x", None, None)
    assert verdict.reproduced is False
    assert "could not replay" in verdict.reason
    assert llm.calls == []  # no model call when replay fails


def test_find_duplicates_keeps_the_earlier_report():
    bugs = [
        {"title": "Total ignores quantity", "page_url": "/cart", "actual": "$12"},
        {"title": "Price shows NaN", "page_url": "/", "actual": "$NaN"},
        {"title": "Cart sum wrong for 2 mugs", "page_url": "/cart", "actual": "$12 not $24"},
    ]
    llm = FakeClient(texts=['{"duplicates": [[1, 3]]}'])  # order given "wrong" way round
    result = find_duplicates(llm, bugs)
    assert result.pairs == [(2, 0)]
    assert llm.calls[0]["cheap"] is True  # dedup uses CHEAP_MODEL


def test_find_duplicates_ignores_invalid_numbers():
    llm = FakeClient(texts=['{"duplicates": [[1, 9], [2, 2], "x"]}'])
    bugs = [{"title": "a", "page_url": "/"}, {"title": "b", "page_url": "/"}]
    assert find_duplicates(llm, bugs).pairs == []


def test_parse_json_object():
    assert parse_json_object('Sure: {"a": 1}') == {"a": 1}
    assert parse_json_object("no json") is None


MORE = {"role": "button", "name": "Increase quantity"}


def test_replay_keeps_a_double_click_a_double_click(context, site_url):
    page = context.new_page()
    replay(page, f"{site_url}/counter.html", [ReplayStep("double_click", {}, MORE)])
    assert page.locator("#quantity").inner_text() == "3"


def test_replay_repeats_reload_and_viewport_changes(context, site_url):
    page = context.new_page()
    replay(
        page,
        f"{site_url}/counter.html",
        [
            ReplayStep("click", {}, MORE),
            ReplayStep("reload", {}, None),
            ReplayStep("set_viewport", {"size": "mobile"}, None),
            ReplayStep("note", {"text": "x"}, None),  # nothing to repeat
        ],
    )
    assert page.locator("#quantity").inner_text() == "1"
    assert page.viewport_size == {"width": 375, "height": 812}


def test_verification_can_look_at_the_page_on_a_phone_screen(context, site_url):
    # A layout bug found on the 375 px screenshot must be checked at 375 px, not on desktop.
    llm = FakeClient(texts=['{"reproduced": true, "reason": "clipped"}'])
    verify_bug(context, llm, f"{site_url}/counter.html", [], "Title clipped", None, None, "mobile")
    image = llm.calls[0]["image"]
    assert int.from_bytes(image[16:20], "big") == 375
    assert "375" in llm.calls[0]["prompt"]
