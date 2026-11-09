import pytest

from worker.agent.policy import Budget, card_number_reason, deny_reason
from worker.safety.actions import ElementInfo


def button(name, **fields) -> ElementInfo:
    return ElementInfo(role="button", name=name, tag="button", **fields)


@pytest.mark.parametrize(
    "name",
    [
        "Pay now",
        "Purchase",
        "Delete account",
        "Remove account",
        "Unsubscribe",
        "Change password",
        "Change email",
        "Send message",
        "Transfer funds",
    ],
)
def test_deny_list_blocks_destructive_buttons(name):
    assert deny_reason(button(name), allow_buy=False)


def test_deny_list_checks_link_urls_and_form_actions():
    assert deny_reason(ElementInfo(role="link", name="Settings", href="/account/delete"), False)
    assert deny_reason(button("OK", form_action="https://site.test/transfer"), False)


@pytest.mark.parametrize("name", ["Add to cart", "Place order", "Log in", "Apply", "Save changes"])
def test_normal_buttons_are_allowed(name):
    assert deny_reason(button(name), allow_buy=False) is None


def test_buy_is_allowed_only_on_the_demo_shop():
    assert deny_reason(button("Buy now"), allow_buy=False)
    assert deny_reason(button("Buy now"), allow_buy=True) is None


def test_words_inside_other_words_dont_match():
    assert deny_reason(button("Repay schedule"), allow_buy=False) is None  # not "pay"
    assert deny_reason(button("Sender details"), allow_buy=False) is None  # not "send"


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
