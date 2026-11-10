"""What the model is told about a page: fields with their state, and messages by position."""

import pytest

from worker.agent.loop import text_changes
from worker.agent.observe import Memory, build_observation, read_page


@pytest.fixture
def state(context, site_url):
    page = context.new_page()
    page.goto(f"{site_url}/fields.html")
    return read_page(page)


def field(state, name):
    return next(e for e in state.elements if e.name == name)


def test_fields_report_required_invalid_and_their_help_text(state):
    email = field(state, "Email")
    assert email.required and email.invalid
    assert email.value == "ada@"
    assert email.described == "We never share your email."
    line = email.describe()
    assert "(required)" in line and "(invalid)" in line
    assert 'help: "We never share your email."' in line


def test_hidden_error_text_is_not_reported(state):
    password = field(state, "Password")
    assert password.described is None and not password.invalid and not password.required


def test_messages_say_which_field_they_sit_next_to(state):
    near = {m.text: m.near for m in state.messages}
    email, city = field(state, "Email"), field(state, "City")
    # Same group as the email field, whatever the words say: that is where the user sees it.
    assert near["Wrong password."] == email.id
    # No shared group: the closest field on the screen.
    assert near["City is required."] == city.id
    # Far from every field.
    assert near["Your session will expire soon."] is None


def test_observation_lists_messages_with_their_field(state):
    text = build_observation(state, "TASK", "STEP 1", [], Memory())
    email = field(state, "Email")
    assert "MESSAGES ON THE PAGE" in text
    assert f'- "Wrong password." (next to [{email.id}] textbox "Email")' in text
    assert '- "Your session will expire soon." (not next to a field)' in text


def test_page_without_messages_says_so(context, site_url):
    page = context.new_page()
    page.goto(f"{site_url}/counter.html")
    text = build_observation(read_page(page), "TASK", "STEP 1", [], Memory())
    assert "MESSAGES ON THE PAGE (errors, alerts, status)\n(none)" in text


def test_changed_values_lead_and_show_before_and_after():
    before = "Shop\nSubtotal: $12.00\nItems: 1\nWelcome"
    after = "Shop\nThanks for shopping\nSubtotal: $24.00\nItems: 2\nWelcome"
    assert text_changes(before, after) == (
        "Subtotal: $12.00 → $24.00 | Items: 1 → 2 | Thanks for shopping"
    )


def test_new_lines_with_numbers_come_before_plain_text():
    assert text_changes("Shop", "Shop\nAdded to your cart.\nDiscount: -$1.20") == (
        "Discount: -$1.20 | Added to your cart."
    )


def test_what_changed_keeps_600_characters():
    after = "\n".join(f"Line number {i} of the new content" for i in range(100))
    result = text_changes("", after)
    assert 500 < len(result) <= 600 and result.endswith("…")
