"""Run 7, M4: critical flows: the episode's answer, the saved script, and replay without a model."""

from types import SimpleNamespace

from worker.flows import flow_task, parse_finish, replay_flow, script_from_steps


def step(action, at, element=None, result="ok", blocked=False, **args):
    """A StepRecord-like step taken on page `at`."""
    return SimpleNamespace(
        action=action, url=at, element=element, result=result, blocked=blocked, args=args
    )


def test_the_episode_task_names_the_journey_and_how_to_finish():
    task = flow_task("Checkout", "Add an item and place the order.")
    assert 'CRITICAL FLOW "Checkout": Add an item and place the order.' in task
    assert "PASSED:" in task and "FAILED:" in task
    # Run 7, M4: a bug seen on the way is reported, but the journey still passes.
    assert "doesn't stop the journey" in task and "still finish with PASSED" in task


def test_a_check_matches_whatever_the_numbers_are():
    from worker.flows import shows

    assert shows(
        "Thanks! Your order #12345 is on its way", "Thanks! Your order #50524 is on its way"
    )
    assert shows("ORDER CONFIRMED", "Order confirmed")
    assert not shows("Your cart is empty", "Order confirmed")
    assert shows("Saved: Ada", "Saved")


def test_a_passed_finish_gives_its_quoted_checks():
    passed, checks, detail = parse_finish(
        "PASSED: the page said \"Order confirmed\" and 'Thank you'"
    )
    assert passed is True and checks == ["Order confirmed", "Thank you"]
    assert detail.startswith("the page said")


def test_a_failed_or_unclear_finish():
    assert parse_finish("FAILED: Save did nothing")[:2] == (False, [])
    # A failure keeps only what it expected (quotes after "expected"): the next run checks it
    # without a model. Texts it saw along the way aren't checks.
    assert parse_finish('FAILED: nothing, expected "Profile saved"')[:2] == (
        False,
        ["Profile saved"],
    )
    seen_only = 'FAILED: the page said "Order confirmed" but order "#1001" showed "#1002"'
    assert parse_finish(seen_only)[1] == []
    assert parse_finish("I tested the site")[0] is None
    assert parse_finish(None) == (None, [], "")


def test_the_script_keeps_effective_actions_with_their_elements():
    name = {"role": "textbox", "name": "Display name"}
    save = {"role": "button", "name": "Save changes"}
    steps = [
        step("navigate", "http://shop.test/", url="/profile"),
        step("type", "http://shop.test/profile", name, text="Test User"),
        step("note", "http://shop.test/profile", text="before"),
        step(
            "click",
            "http://shop.test/profile",
            {"role": "button", "name": "Gone"},
            result="error: no such element",
        ),
        step("click", "http://shop.test/profile", save, blocked=True),
        step("click", "http://shop.test/profile", save),
        step("finish", "http://shop.test/profile", summary="PASSED"),
    ]
    script = script_from_steps("http://shop.test/", steps, ["Profile saved."])
    assert [s["action"] for s in script["steps"]] == ["navigate", "type", "click"]
    assert script["steps"][1] == {
        "action": "type",
        "args": {"text": "Test User"},
        "element": name,
        "url": "http://shop.test/profile",
    }
    assert script["steps"][0]["args"] == {"url": "/profile"}
    assert script["checks"] == ["Profile saved."] and script["end_path"] == "/profile"
    assert script["failing"] is False
    assert script_from_steps("http://shop.test/", steps, ["x"], failing=True)["failing"] is True
    assert script_from_steps("http://shop.test/", [step("note", "http://shop.test/")], []) is None


def test_a_saved_journey_replays_without_a_model(context, site_url):
    script = {
        "start_url": f"{site_url}/form.html",
        "steps": [
            {
                "action": "type",
                "args": {"text": "Ada"},
                "element": {"role": "textbox", "name": "Name"},
                "url": f"{site_url}/form.html",
            },
            {
                "action": "click",
                "args": {},
                "element": {"role": "button", "name": "Save"},
                "url": f"{site_url}/form.html",
            },
        ],
        "checks": ["Saved"],
        "end_path": "/form.html",
    }
    result, detail = replay_flow(context, script)
    assert result == "ok", detail


def test_a_replay_that_breaks_says_where(context, site_url):
    script = {
        "start_url": f"{site_url}/form.html",
        "steps": [
            {
                "action": "click",
                "args": {},
                "element": {"role": "button", "name": "No such button"},
                "url": f"{site_url}/form.html",
            }
        ],
        "checks": [],
        "end_path": "/form.html",
    }
    result, detail = replay_flow(context, script)
    assert result == "broken" and "step 1" in detail and "click" in detail


def test_a_replay_whose_check_is_missing_fails(context, site_url):
    script = {
        "start_url": f"{site_url}/form.html",
        "steps": [],
        "checks": ["Order confirmed"],
        "end_path": "/form.html",
    }
    script["steps"] = [
        {"action": "reload", "args": {}, "element": None, "url": f"{site_url}/form.html"}
    ]
    result, detail = replay_flow(context, script)
    assert result == "checks_failed" and '"Order confirmed"' in detail


def test_a_signed_in_run_tells_the_journey_its_credentials_are_hidden():
    # Run 7, M6: a sign-in journey on a target with a saved login saw "[test account]" and failed.
    assert "[test account]" not in flow_task("Sign in", "Sign in.")
    note = flow_task("Sign in", "Sign in.", signed_in=True)
    assert "already signed in" in note and "[test account]" in note


def test_checks_are_kept_only_if_the_final_page_agrees():
    from worker.flows import checks_for_final_page

    final = "Order confirmed. Thanks! Your order #123 is on its way"
    # A PASSED quote from an earlier page ("Go to checkout") would fail every replay.
    assert checks_for_final_page(True, ["Order confirmed", "Go to checkout"], final) == [
        "Order confirmed"
    ]
    # An expected-but-missing FAILED check must really be missing from the final page.
    assert checks_for_final_page(False, ["Profile saved", "Order confirmed"], final) == [
        "Profile saved"
    ]
