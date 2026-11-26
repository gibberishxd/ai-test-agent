"""Reproduce run 9's deep-mode reports by hand: 5 on the clean shop, 8 unmatched on the buggy shop.

Prints one line of measurements per report and saves a screenshot per report to OUT.
"""

import html
import sys
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

CLEAN, BUGGY = "http://localhost:5174", "http://localhost:5173"
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
DESKTOP, TABLET, PHONE = (1440, 900), (768, 1024), (390, 844)


def shot(page: Page, name: str, full: bool = False) -> None:
    page.wait_for_timeout(300)
    page.screenshot(path=str(OUT / f"{name}.jpg"), type="jpeg", quality=70, full_page=full)


def badge(page: Page) -> str:
    return page.locator("nav").get_by_role("link", name="Cart (").inner_text()


def sign_in(page: Page, base: str) -> None:
    page.goto(f"{base}/login")
    hint = page.get_by_text("Demo account:").inner_text().split(":", 1)[1]
    email, password = [s.strip() for s in hint.split("/")]
    page.locator("#email").fill(email)
    page.locator("#password").fill(password)
    page.locator("#password").press("Enter")
    page.wait_for_url(lambda url: "/login" not in url)


def add(page: Page, product: int, quantity: str | None = None) -> None:
    page.get_by_role("link", name="Shop", exact=True).click()
    page.locator(f'a[href="/products/{product}"]').first.click()
    if quantity is not None:
        page.get_by_role("spinbutton", name="Quantity").fill(quantity)
    page.get_by_role("button", name="Add to cart").click()
    page.get_by_role("status").wait_for()


def text_page(page: Page, title: str, body: str) -> None:
    page.set_content(f"<h3>{html.escape(title)}</h3><pre style='white-space:pre-wrap'>{html.escape(body)}</pre>")


with sync_playwright() as p:
    browser = p.chromium.launch()

    def new(base: str, size=DESKTOP) -> Page:
        page = browser.new_page(viewport={"width": size[0], "height": size[1]})
        page.goto(base)
        return page

    # ---- clean shop -------------------------------------------------------------------
    page = new(CLEAN)
    add(page, 4, "999999")
    after_big = badge(page)
    add(page, 4, "1.5")
    page.get_by_role("link", name="Cart (").click()
    page.get_by_test_id("cart-total").wait_for()
    print(f"C1 quantity: after 999999 -> {after_big}; after 1.5 -> {badge(page)};",
          "cart total", page.get_by_test_id("cart-total").inner_text())
    shot(page, "c1-quantity-cart")
    page.close()

    page = new(CLEAN)
    page.get_by_role("button", name="Search").click()
    page.get_by_role("searchbox", name="Search products").fill("mug")
    page.wait_for_timeout(300)
    while_typing = page.locator(".card").count()
    page.get_by_role("link", name="Profile").click()
    page.get_by_role("link", name="Shop", exact=True).click()
    page.locator(".card").first.wait_for()
    print(f"C2 search: {while_typing} card(s) while 'mug' typed; back on Shop the box holds",
          repr(page.get_by_role("searchbox").input_value()), "and", page.locator(".card").count(), "cards show")
    shot(page, "c2-search-kept-list-unfiltered")
    page.close()

    page = new(CLEAN)
    add(page, 1)
    page.get_by_role("link", name="Profile").click()
    via_header = badge(page)
    page.get_by_role("link", name="Returns policy").click()
    page.wait_for_url("**/returns")
    page.wait_for_load_state()
    print(f"C3 footer link: header link keeps {via_header}; footer link -> {page.url} shows {badge(page)}")
    shot(page, "c3-footer-link-cart-empty")
    page.close()

    page = new(CLEAN)
    button = page.get_by_role("button", name="Search")
    button.click()
    attrs = {a: button.get_attribute(a) for a in ("aria-expanded", "aria-controls", "aria-pressed")}
    page.get_by_role("searchbox").focus()
    page.keyboard.press("Escape")
    still_open = page.locator("#search-input").count() == 1
    print(f"C4 search toggle: {attrs}; field still open after Escape: {still_open}")
    shot(page, "c4-search-open-after-escape")
    page.close()

    page = new(CLEAN, TABLET)
    sign_in(page, CLEAN)
    measure = """t => { const td = t.querySelector('td'), th = t.querySelector('th'), cs = getComputedStyle;
      return {width: Math.round(t.getBoundingClientRect().width), tdPadding: cs(td).padding,
              tdBorderBottom: cs(td).borderBottomWidth, thAlign: cs(th).textAlign}; }"""
    page.goto(f"{CLEAN}/orders/1003")
    order = page.locator("table").evaluate(measure)
    shot(page, "c5-order-table")
    page.goto(CLEAN)
    add(page, 1)
    page.get_by_role("link", name="Cart (").click()
    cart = page.locator("table").evaluate(measure)
    shot(page, "c5-cart-table-for-comparison")
    print(f"C5 tables at 768 px: order {order}; cart {cart}")
    page.close()

    # ---- buggy shop -------------------------------------------------------------------
    page = new(BUGGY)
    response = page.goto(f"{BUGGY}/return-policy")
    print(f"B1/B2 /return-policy: HTTP {response.status}; main landmarks {page.locator('main').count()};",
          "reached only from the buggy footer link:",
          page.evaluate("1") and "yes (clean footer links to /returns)")
    shot(page, "b1-b2-return-policy-404")
    page.close()

    page = new(BUGGY)
    head = page.evaluate("document.head.outerHTML")
    clean_head = new(CLEAN).evaluate("document.head.outerHTML")
    print(f"B3 metadata: og/twitter/canonical tags on buggy: {head.count('og:') + head.count('twitter:') + head.count('canonical')};",
          f"same <head> as the clean build: {head == clean_head}")
    import re
    shown = re.sub(r"<style[^>]*>.*?</style>|<script[^>]*>.*?</script>", "", head, flags=re.S)
    text_page(page, "<head> of http://localhost:5173/ without the dev server's inline styles and scripts (the clean build's is identical)", shown)
    shot(page, "b3-head-without-metadata")
    page.close()

    page = new(BUGGY)
    sign_in(page, BUGGY)
    page.goto(f"{BUGGY}/orders")
    before = page.locator("main a[href^='/orders/']").count()
    page.goto(BUGGY)
    add(page, 1)
    requests: list[str] = []
    page.on("request", lambda r: requests.append(f"{r.method} {r.url}") if r.resource_type in ("fetch", "xhr") else None)
    page.get_by_role("link", name="Cart (").click()
    page.get_by_role("link", name="Checkout").click()
    page.locator("#name").fill("Test Shopper")
    page.locator("#email").fill("shopper@example.com")
    page.locator("#card").fill("4242424242424242")
    page.get_by_role("button", name="Place order").click()
    confirmation = page.get_by_role("status").inner_text()
    shot(page, "b4-order-confirmation")
    page.get_by_role("link", name="My orders").click()
    page.locator("main a[href^='/orders/']").first.wait_for()
    after = page.locator("main a[href^='/orders/']").count()
    print(f"B4 orders: confirmation {confirmation!r}; requests on Place order {requests};",
          f"orders listed before {before}, after {after}")
    shot(page, "b4-my-orders-unchanged")
    page.close()

    page = new(BUGGY)
    add(page, 1, "99")
    print(f"B5 quantity 99: badge {badge(page)}")
    shot(page, "b5-quantity-99")
    page.close()

    page = new(BUGGY)
    add(page, 1)
    before = badge(page)
    page.goto(f"{BUGGY}/cart")
    page.get_by_text("Your cart is empty").wait_for()
    stored = page.evaluate("Object.keys(localStorage)")
    print(f"B6 reload: {before} before a full load of /cart, {badge(page)} after; localStorage keys {stored}")
    shot(page, "b6-cart-empty-after-reload")
    page.close()

    page = new(BUGGY, PHONE)
    sign_in(page, BUGGY)
    page.goto(BUGGY)
    sizes = page.evaluate("""() => [...document.querySelectorAll('nav a, nav button, .card-title a')]
      .map(e => { const r = e.getBoundingClientRect();
                  return `${(e.innerText || e.getAttribute('aria-label') || '?').trim()} ${Math.round(r.width)}x${Math.round(r.height)}`; })""")
    print(f"B7 tap targets at 390 px: {sizes}")
    shot(page, "b7-header-at-390px")
    page.close()

    page = new(BUGGY)
    add(page, 1)
    page.get_by_role("link", name="Cart (").click()
    page.get_by_role("button", name="Apply").click()
    message = page.get_by_text("That code isn't valid.")
    info = message.evaluate("""e => ({tag: e.tagName, role: e.getAttribute('role'), live: e.getAttribute('aria-live'),
      liveRegionsInMain: document.querySelectorAll('main [role=status], main [role=alert], main [aria-live]').length,
      inputInvalid: document.querySelector('#discount').getAttribute('aria-invalid'),
      inputDescribedBy: document.querySelector('#discount').getAttribute('aria-describedby')})""")
    print(f"B8 discount message: {info}")
    shot(page, "b8-discount-message")
    page.close()

    browser.close()
