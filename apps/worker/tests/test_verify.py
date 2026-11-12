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
    assert verdict.replayed is False  # the run summary then says "could not replay: ..."
    assert 'no button "Does not exist"' in verdict.reason
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


# --- exact targets: never click "the first one" ------------------------------------------------

import pytest  # noqa: E402

from worker.verify import ReplayError  # noqa: E402

ADD = {"role": "button", "name": "Add to cart", "nth": 3, "count": 6, "context": "Product 4"}


def cart_after(context, site_url, element):
    page = context.new_page()
    replay(page, f"{site_url}/cards.html", [ReplayStep("click", {}, element)])
    return page.locator("#cart").inner_text()


def test_replay_picks_the_button_in_the_right_card(context, site_url):
    assert cart_after(context, site_url, {**ADD, "css": None}) == "Cart: Product 4"


def test_replay_uses_the_css_path_when_surroundings_dont_settle_it(context, site_url):
    element = {**ADD, "context": "Gone", "css": "main > section > article:nth-of-type(5) > button"}
    assert cart_after(context, site_url, element) == "Cart: Product 5"


def test_replay_uses_the_position_only_when_the_page_has_the_same_shape(context, site_url):
    element = {**ADD, "nth": 1, "context": None, "css": None}
    assert cart_after(context, site_url, element) == "Cart: Product 2"


def test_replay_fails_loudly_instead_of_clicking_the_first_match(context, site_url):
    element = {**ADD, "count": 7, "context": "Gone", "css": None}  # the page changed shape
    with pytest.raises(ReplayError, match='6 elements match button "Add to cart"'):
        cart_after(context, site_url, element)


def test_replay_fails_loudly_when_the_element_is_gone(context, site_url):
    element = {"role": "button", "name": "Remove all", "nth": 0, "count": 1}
    with pytest.raises(ReplayError, match='no button "Remove all" on the page'):
        cart_after(context, site_url, element)


def test_unreplayable_bug_says_could_not_replay(context, site_url):
    element = {"role": "button", "name": "Remove all", "nth": 0, "count": 1}
    verdict = verify_bug(
        context,
        FakeClient(),
        f"{site_url}/cards.html",
        [ReplayStep("click", {}, element)],
        "x",
        None,
        None,
    )
    assert not verdict.reproduced and not verdict.replayed
    assert verdict.reason.startswith('step 1 (click): no button "Remove all" on the page')


def test_replay_resolves_a_relative_navigate(context, site_url):
    page = context.new_page()
    replay(page, f"{site_url}/form.html", [ReplayStep("navigate", {"url": "/cards.html"}, None)])
    assert page.url == f"{site_url}/cards.html"


def test_a_number_field_is_a_spinbutton_and_replay_can_type_into_it(context, site_url):
    # A number input's role is "spinbutton" (ARIA), not "textbox": calling it a textbox made
    # replay look for an element that doesn't exist and dismiss correct bug reports.
    from worker.agent.observe import read_page

    page = context.new_page()
    page.goto(f"{site_url}/number.html")
    roles = {e.name: e.role for e in read_page(page).elements}
    assert roles == {"Quantity": "spinbutton", "Email": "textbox"}

    fresh = context.new_page()
    target = {"role": "spinbutton", "name": "Quantity", "nth": 0, "count": 1}
    replay(fresh, f"{site_url}/number.html", [ReplayStep("type", {"text": "3"}, target)])
    assert fresh.locator("#echo").inner_text() == "Quantity is 3"


def test_replay_finds_a_field_by_its_label_when_the_recorded_role_is_off(context, site_url):
    # Runs recorded before the fix stored "textbox" for number fields.
    page = context.new_page()
    target = {"role": "textbox", "name": "Quantity", "nth": 0, "count": 1}
    replay(page, f"{site_url}/number.html", [ReplayStep("type", {"text": "4"}, target)])
    assert page.locator("#echo").inner_text() == "Quantity is 4"


# --- Run 3, H1: replay on single-page apps and specific failure reasons ------------------------

SOCKS = {"role": "link", "name": "Wool Socks"}
QUANTITY = {"role": "spinbutton", "name": "Quantity"}
ADD_TO_CART = {"role": "button", "name": "Add to cart"}


def test_replay_waits_for_a_route_that_renders_after_a_client_side_navigation(context, site_url):
    # A pushState link changes the URL without a page load, so "network idle" is already true
    # and the next step used to look for the field before the route had drawn it (run be495c9f).
    page = context.new_page()
    replay(
        page,
        f"{site_url}/spa.html",
        [
            ReplayStep("click", {}, SOCKS),
            ReplayStep("type", {"text": "3"}, QUANTITY),
            ReplayStep("click", {}, ADD_TO_CART),
        ],
    )
    assert page.locator("#cart").inner_text() == "Cart (3)"


def test_a_missing_element_is_reported_as_such_with_its_step(context, site_url):
    missing = ReplayStep("click", {}, {"role": "button", "name": "Does not exist"})
    verdict = verify_bug(context, FakeClient(), f"{site_url}/form.html", [missing], "x", None, None)
    assert verdict.failure == {
        "kind": "element_not_found",
        "step": 1,
        "action": "click",
        "detail": 'no button "Does not exist" on the page',
    }


def test_an_ambiguous_element_is_reported_as_such(context, site_url):
    # cards.html has several identical buttons; a recording without a place can't pick one.
    twin = ReplayStep("click", {}, {"role": "button", "name": "Add to cart"})
    verdict = verify_bug(context, FakeClient(), f"{site_url}/cards.html", [twin], "x", None, None)
    assert verdict.failure["kind"] == "ambiguous_element"


def test_a_navigation_that_fails_is_reported_as_such(context, site_url):
    gone = ReplayStep("navigate", {"url": "http://127.0.0.1:9/nowhere"}, None)
    verdict = verify_bug(context, FakeClient(), f"{site_url}/form.html", [gone], "x", None, None)
    assert verdict.failure["kind"] == "navigation_error"
    assert verdict.failure["step"] == 1


def test_the_judge_sees_the_page_the_last_step_led_to_not_the_one_before(context, site_url):
    # After a client-side link the URL changes first and the page is drawn a moment later: the
    # judge was shown /cart's URL with the product page's text (run be495c9f, bug 5).
    llm = FakeClient(texts=['{"reproduced": true, "reason": "x"}'])
    view_cart = ReplayStep("click", {}, {"role": "link", "name": "View cart"})
    verify_bug(context, llm, f"{site_url}/spa.html", [view_cart], "x", None, None)
    assert "Your cart" in llm.calls[0]["prompt"]


# --- K1: judge a change, not one screenshot -----------------------------------------------------

PROFILE_NAME = {"role": "textbox", "name": "Display name"}
SAVE_CHANGES = {"role": "button", "name": "Save changes"}
NO_EFFECT_STEPS = [
    ReplayStep("type", {"text": "New Name"}, PROFILE_NAME),
    ReplayStep("click", {}, SAVE_CHANGES),
]


def test_a_dead_button_reported_as_doing_nothing_is_confirmed_without_a_model_call(
    context, site_url
):
    llm = FakeClient(texts=['{"reproduced": false, "reason": "the page looks normal"}'])
    verdict = verify_bug(
        context,
        llm,
        f"{site_url}/state/dead.html",
        NO_EFFECT_STEPS,
        "'Save changes' on the profile does nothing",
        "The name is saved and a confirmation shows",
        "Nothing happens",
    )
    assert verdict.reproduced is True and verdict.replayed is True
    assert llm.calls == []  # measured, not judged
    assert "changed nothing" in verdict.reason
    assert verdict.diff and verdict.diff["meaningful"] is False


def test_a_no_effect_report_on_a_button_that_works_goes_to_the_judge_with_the_diff(
    context, site_url
):
    llm = FakeClient(texts=['{"reproduced": false, "reason": "Saved appeared"}'])
    verdict = verify_bug(
        context,
        llm,
        f"{site_url}/state/works.html",
        NO_EFFECT_STEPS,
        "'Save changes' does nothing",
        None,
        None,
    )
    assert verdict.reproduced is False
    prompt = llm.calls[0]["prompt"]
    assert "WHAT CHANGED" in prompt and "Saved" in prompt
    assert verdict.diff["meaningful"] is True


def test_the_judge_gets_before_and_after_in_one_picture(context, site_url):
    import io

    from PIL import Image

    llm = FakeClient(texts=['{"reproduced": true, "reason": "x"}'])
    verify_bug(context, llm, f"{site_url}/state/works.html", NO_EFFECT_STEPS, "x", None, None)
    picture = Image.open(io.BytesIO(llm.calls[0]["image"]))
    page_width = 1280
    assert picture.width > page_width  # two screenshots side by side (each scaled to ≤1024)


def test_a_wrong_change_report_is_judged_with_the_diff(context, site_url):
    llm = FakeClient(texts=['{"reproduced": true, "reason": "total stayed $12"}'])
    plus = {"role": "button", "name": "Increase quantity"}
    verdict = verify_bug(
        context,
        llm,
        f"{site_url}/state/wrong-total.html",
        [ReplayStep("click", {}, plus)],
        "Cart total ignores quantity",
        "$24.00",
        "$12.00",
    )
    assert verdict.reproduced is True
    prompt = llm.calls[0]["prompt"]
    assert "Socks × 2" in prompt and "Totals unchanged: Total: $12.00" in prompt


def test_a_spinner_and_a_clock_dont_hide_a_dead_button(context, site_url):
    verdict = verify_bug(
        context,
        FakeClient(),
        f"{site_url}/state/noisy.html",
        NO_EFFECT_STEPS,
        "Save changes does nothing",
        None,
        None,
    )
    assert verdict.reproduced is True


def test_a_dead_click_on_something_that_isnt_a_control_still_goes_to_the_judge(context, site_url):
    """Clicking a paragraph is expected to do nothing; only the judge can say if that's a bug."""
    llm = FakeClient(texts=['{"reproduced": false, "reason": "plain text"}'])
    verdict = verify_bug(
        context,
        llm,
        f"{site_url}/state/dead.html",
        [ReplayStep("click", {}, {"role": "paragraph", "name": "Hello, Demo User", "css": "#who"})],
        "Clicking the greeting does nothing",
        None,
        None,
    )
    assert verdict.reproduced is False and len(llm.calls) == 1


def test_password_values_never_reach_the_judge(context, site_url):
    llm = FakeClient(texts=['{"reproduced": false, "reason": "x"}'])
    verify_bug(context, llm, f"{site_url}/state/works.html", NO_EFFECT_STEPS, "x", None, None)
    assert "hunter2" not in llm.calls[0]["prompt"]


def test_a_finding_without_steps_is_still_judged_on_one_screenshot(context, site_url):
    llm = FakeClient(texts=['{"reproduced": true, "reason": "x"}'])
    verdict = verify_bug(context, llm, f"{site_url}/form.html", [], "Layout broken", None, None)
    assert verdict.reproduced and verdict.diff is None
    assert "WHAT CHANGED" not in llm.calls[0]["prompt"]


def test_a_no_effect_report_about_clicking_into_a_field_is_dismissed_without_a_model_call(
    context, site_url
):
    """Clicking a number field only focuses it (it doesn't increment): a measured 'nothing
    changed' there is the expected behaviour, not a bug. Seen in the K1 re-check: Gemma's judge
    confirmed 'Quantity spinbutton does not increment value'."""
    llm = FakeClient(texts=['{"reproduced": true, "reason": "no change"}'])
    verdict = verify_bug(
        context,
        llm,
        f"{site_url}/number.html",
        [ReplayStep("click", {}, {"role": "spinbutton", "name": "Quantity"})],
        "Quantity spinbutton does not increment value",
        "value goes up",
        "nothing happens",
    )
    assert verdict.reproduced is False and verdict.replayed is True
    assert llm.calls == []
    assert "only focuses" in verdict.reason


def test_a_no_effect_report_on_a_form_the_browser_blocked_is_not_confirmed_by_measurement(
    context, site_url
):
    llm = FakeClient(texts=['{"reproduced": false, "reason": "the browser asked for the name"}'])
    verdict = verify_bug(
        context,
        llm,
        f"{site_url}/state/validation.html",
        [ReplayStep("click", {}, {"role": "button", "name": "Book now"})],
        "Book now button fails to process booking with missing required fields",
        None,
        "Nothing on the page changed",
    )
    assert verdict.reproduced is False and len(llm.calls) == 1
    assert "browser refused to submit" in llm.calls[0]["prompt"]
