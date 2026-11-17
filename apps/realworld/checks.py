"""Scripted reproduction checks for the real-world bugs (run 8, N4).

Each check drives the app at the fix's parent like the issue's reporter did and returns
(reproduced?, what it saw). A bug whose check fails is dropped from the measurement.
"""

from playwright.sync_api import Page


def _text(page: Page) -> str:
    return page.evaluate("() => document.body.innerText") or ""


def it1_roman_invalid(page: Page, base: str) -> tuple[bool, str]:
    page.goto(f"{base}/roman-numeral-converter")
    page.wait_for_timeout(2000)
    page.locator("input[placeholder='Please Input']").nth(1).fill("IVX")
    page.wait_for_timeout(800)
    body = _text(page)
    section = body[body.find("Roman to arabic") :][:120]
    shown = section.split("\n")[1].strip() if "\n" in section else ""
    flagged = any(w in section.lower() for w in ("invalid", "not valid", "valid roman"))
    return shown == "4" and not flagged, f"'IVX' → {shown!r}, flagged as invalid: {flagged}"


def it2_ipv4_readonly(page: Page, base: str) -> tuple[bool, str]:
    page.goto(f"{base}/ipv4-address-converter")
    page.wait_for_timeout(2000)
    field = page.locator("input[placeholder^='The ipv4 address']")
    before = field.input_value()
    readonly = field.get_attribute("readonly") is not None
    field.click()
    page.keyboard.press("End")
    page.keyboard.type("0")
    after = field.input_value()
    return readonly and after == before, (
        f"readonly attribute: {readonly}; typing '0' at the end: {before!r} → {after!r}"
    )


def it3_rc4_decrypt(page: Page, base: str) -> tuple[bool, str]:
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)[:120]))
    page.goto(f"{base}/encryption")
    page.wait_for_timeout(2000)
    before = _text(page).count("Your decrypted text")
    page.locator(".c-select-input").nth(1).click()  # the Decrypt panel's algorithm
    page.wait_for_timeout(500)
    option = page.locator(".c-select-dropdown-option:visible", has_text="RC4")
    option.hover()
    page.mouse.down()
    page.mouse.up()
    page.wait_for_timeout(1500)
    after = _text(page).count("Your decrypted text")
    gone = before == 1 and after == 0
    return (
        gone,
        f"decrypt panel before: {before}, after choosing RC4: {after}; errors: {errors[:2]}",
    )


def it4_favorite_on_tool_page(page: Page, base: str) -> tuple[bool, str]:
    page.goto(f"{base}/token-generator")
    page.wait_for_timeout(2000)
    before = page.evaluate("() => localStorage.getItem('favoriteToolsName')")
    favorite = page.locator("button.c-button.circle[style*='opacity']").first  # the faint heart
    favorite.click()
    page.wait_for_timeout(800)
    after = page.evaluate("() => localStorage.getItem('favoriteToolsName')")
    page.goto(f"{base}/")
    page.wait_for_timeout(1500)
    home = _text(page).lower()
    listed = "your favorite tools" in home
    added = bool(after) and after != before and "token" in (after or "").lower()
    return (not added and not listed), (
        f"favorites before {before!r}, after clicking on the tool page {after!r}; "
        f"home lists favorites: {listed}"
    )


def it5_otp_lowercase(page: Page, base: str) -> tuple[bool, str]:
    page.goto(f"{base}/otp-generator")
    page.wait_for_timeout(2000)
    secret = page.locator("input[placeholder^='Paste your TOTP secret']")
    secret.fill("abcd")
    page.wait_for_timeout(800)
    lower = "should be a base32 string" in _text(page)
    secret.fill("ABCD")
    page.wait_for_timeout(800)
    upper = "should be a base32 string" in _text(page)
    return lower and not upper, f"'abcd' rejected: {lower}; 'ABCD' rejected: {upper}"


def _ra_login(page: Page, base: str) -> None:
    page.goto(f"{base}/#/login")
    page.wait_for_timeout(4000)
    page.fill("input[name=username]", "demo")  # the login page's own hint: demo / demo
    page.fill("input[name=password]", "demo")
    page.click("button[type=submit]")
    page.wait_for_timeout(5000)


def ra1_clear_filters(page: Page, base: str) -> tuple[bool, str]:
    _ra_login(page, base)
    page.goto(f"{base}/#/orders")
    page.wait_for_timeout(4000)
    before = page.locator("tbody tr").count()
    page.get_by_role("button", name="Add filter").click()
    page.wait_for_timeout(800)
    page.get_by_role("menuitem", name="Remove all filters").click()
    page.wait_for_timeout(3000)
    after = page.locator("tbody tr").count()
    total = [line for line in _text(page).split("\n") if " of " in line][:1]
    return (
        before > 0 and after == 0,
        f"rows before {before}, after 'Remove all filters' {after} {total}",
    )


def ra2_prev_next_index(page: Page, base: str) -> tuple[bool, str]:
    import re

    _ra_login(page, base)
    page.goto(f"{base}/#/orders")
    page.wait_for_timeout(4000)
    page.get_by_role("tab").nth(1).click()  # Delivered: several pages
    page.wait_for_timeout(2000)
    page.get_by_role("button", name="Go to page 2", exact=True).click()
    page.wait_for_timeout(3000)
    page.locator("tbody tr").nth(3).click()  # the 4th order on page 2: position 29
    page.wait_for_timeout(3000)
    shown = re.findall(r"\b(\d+) / (\d+)\b", _text(page))[:1]
    position = int(shown[0][0]) if shown else None
    return position is not None and position != 29, f"4th order of page 2 shows {shown}"


def ra3_tabbed_form(page: Page, base: str) -> tuple[bool, str]:
    _ra_login(page, base)
    page.goto(f"{base}/#/products/1")
    page.wait_for_timeout(5000)
    page.get_by_role("tab").nth(1).click()
    page.wait_for_timeout(2000)
    selected = page.locator("[role=tab][aria-selected=true]").all_inner_texts()
    return selected[:1] != [
        "DETAILS"
    ], f"after clicking the 2nd tab: {page.url}, selected {selected}"


CHECKS = {
    "IT-1": it1_roman_invalid,
    "IT-2": it2_ipv4_readonly,
    "IT-3": it3_rc4_decrypt,  # dropped: see bugs.json
    "IT-4": it4_favorite_on_tool_page,
    "IT-5": it5_otp_lowercase,
    "RA-1": ra1_clear_filters,
    "RA-2": ra2_prev_next_index,
    "RA-3": ra3_tabbed_form,  # dropped: see bugs.json
}
