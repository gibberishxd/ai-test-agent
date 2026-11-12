import pytest

from worker.agent.policy import Budget, card_number_reason, deny_reason
from worker.safety.actions import ElementInfo


def button(name, **fields) -> ElementInfo:
    return ElementInfo(role="button", name=name, tag="button", **fields)


# (what the user sees on the control, the category safe mode files it under)
BLOCKED_BUTTONS = [
    ("Pay now", "payment"),
    ("PAY", "payment"),
    ("Purchase", "payment"),
    ("Buy now", "payment"),
    ("Place order", "payment"),
    ("Place your order", "payment"),
    ("Complete purchase", "payment"),
    ("Complete my order", "payment"),
    ("Submit payment", "payment"),
    ("Confirm", "commitment"),
    ("Confirm booking", "commitment"),
    ("Subscribe", "subscription"),
    ("Unsubscribe", "subscription"),
    ("Cancel subscription", "subscription"),
    ("Cancel my plan", "subscription"),
    ("Delete account", "destructive"),
    ("delete", "destructive"),
    ("Remove item", "destructive"),
    ("Deactivate", "destructive"),
    ("Close account", "destructive"),
    ("Close my account", "destructive"),
    ("Change password", "account"),
    ("Change your email", "account"),
    ("Send message", "outbound"),
    ("Transfer funds", "outbound"),
]


@pytest.mark.parametrize(("name", "category"), BLOCKED_BUTTONS)
def test_deny_list_blocks_final_and_destructive_actions(name, category):
    reason = deny_reason(button(name), is_demo_target=False)
    assert reason and category in reason


ALLOWED_BUTTONS = [
    "Add to cart",
    "Log in",
    "Apply",
    "Save changes",
    "Search",
    "Checkout",  # going to the checkout page commits nothing
    "Continue",
    "Cancel",  # backing out of a dialog
    "Close",
    "Repay schedule",  # not "pay"
    "Sender details",  # not "send"
    "Removal policy",  # not "remove"
    "Confirmation emails",  # not "confirm"
]


@pytest.mark.parametrize("name", ALLOWED_BUTTONS)
def test_normal_buttons_are_allowed(name):
    assert deny_reason(button(name), is_demo_target=False) is None


# Every place a control can say what it does, not only its visible text.
BLOCKED_BY_FIELD = [
    ("aria-label", button("", aria_label="Delete account")),
    ("value", ElementInfo(role="button", tag="input", input_type="submit", value="Place order")),
    ("form action", button("Continue", form_action="https://site.test/orders/place-order")),
    ("form action", button("OK", form_action="https://site.test/transfer")),
    ("link", ElementInfo(role="link", name="Settings", href="/account/delete")),
    ("link", ElementInfo(role="link", name="Manage", href="/billing/cancelSubscription?id=7")),
    ("link", ElementInfo(role="link", name="Bye", href="https://site.test/close_account")),
]


@pytest.mark.parametrize(("field", "element"), BLOCKED_BY_FIELD)
def test_deny_list_reads_every_field_that_names_the_action(field, element):
    reason = deny_reason(element, is_demo_target=False)
    assert reason and field in reason


def test_deny_list_ignores_what_is_typed_in_a_text_field():
    # A search box containing "delete" is not a delete button.
    field = ElementInfo(role="textbox", name="Search", tag="input", value="how to delete")
    assert deny_reason(field, is_demo_target=False) is None


def test_the_demo_shops_are_the_only_exception():
    # They are ours and fake: placing an order there is the point of the demo.
    assert deny_reason(button("Place order"), is_demo_target=True) is None
    assert deny_reason(button("Delete account"), is_demo_target=True) is None
    assert deny_reason(button("Place order"), is_demo_target=False)


def test_card_numbers_only_on_the_demo_shop():
    assert card_number_reason("4242 4242 4242 4242", is_demo_target=False)
    assert card_number_reason("4242 4242 4242 4242", is_demo_target=True) is None
    assert card_number_reason("test+1@example.com", is_demo_target=False) is None


def test_budget_stops_at_max_steps():
    budget = Budget(max_steps=2, max_seconds=60, max_cost_usd=1)
    budget.record("click", {"element_id": 1}, 0)
    assert budget.exhausted() is None
    budget.record("click", {"element_id": 2}, 0)
    assert "step" in budget.exhausted()


def test_budget_stops_at_max_cost():
    budget = Budget(max_steps=10, max_seconds=60, max_cost_usd=0.10)
    budget.record("click", {"element_id": 1}, 0.11)
    assert "cost" in budget.exhausted()


def test_budget_stops_at_max_time():
    budget = Budget(max_steps=10, max_seconds=0, max_cost_usd=1)
    assert "time" in budget.exhausted()


def test_loop_detection_ignores_reasoning_differences():
    budget = Budget(max_steps=10, max_seconds=60, max_cost_usd=1)
    assert budget.record("click", {"element_id": 4, "reasoning": "a"}, 0) is None
    assert budget.record("click", {"element_id": 4, "reasoning": "b"}, 0) is None
    assert "loop" in budget.record("click", {"element_id": 4, "reasoning": "c"}, 0)


def test_different_actions_dont_count_as_a_loop():
    budget = Budget(max_steps=10, max_seconds=60, max_cost_usd=1)
    for element_id in (1, 2, 1, 2):
        assert budget.record("click", {"element_id": element_id}, 0) is None


def test_repeats_that_change_the_page_are_not_a_loop():
    # Clicking "+" three times is testing, not being stuck.
    budget = Budget(max_steps=10, max_seconds=60, max_cost_usd=1)
    for _ in range(3):
        assert budget.record("click", {"element_id": 4}, 0, changed=True) is None
    assert not budget.repeating()


def test_a_change_resets_the_count_of_repeats_without_effect():
    budget = Budget(max_steps=10, max_seconds=60, max_cost_usd=1)
    for changed in (False, False, True, False, False):
        assert budget.record("click", {"element_id": 4}, 0, changed=changed) is None
    assert budget.repeating()  # one more without effect ends the run
    assert "without changing" in budget.record("click", {"element_id": 4}, 0, changed=False)


def test_endless_repeats_are_a_loop_even_when_the_page_changes():
    # "Add to cart" forever changes the page every time, and is still a loop.
    budget = Budget(max_steps=20, max_seconds=60, max_cost_usd=1)
    for _ in range(4):
        assert budget.record("click", {"element_id": 4}, 0, changed=True) is None
    assert not budget.repeating()
    assert budget.record("click", {"element_id": 4}, 0, changed=True) is None
    assert budget.repeating()
    assert "loop" in budget.record("click", {"element_id": 4}, 0, changed=True)
