"""The two reports first seen in the 2026-11-26 re-run, reproduced on the clean shop (5174)."""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

CLEAN = "http://localhost:5174"
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch()

    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(CLEAN)
    page.get_by_role("button", name="Search").click()
    box = page.get_by_role("searchbox", name="Search products")
    box.fill("lamp")
    page.wait_for_timeout(300)
    plain = page.locator(".card").count()
    box.fill("lamp ")
    page.wait_for_timeout(300)
    spaced = page.locator(".card").count()
    print(f"R1 search: 'lamp' -> {plain} card(s); 'lamp ' -> {spaced} card(s)")
    page.screenshot(path=str(OUT / "r1-search-trailing-space.jpg"), type="jpeg", quality=70)
    page.close()

    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(f"{CLEAN}/checkout")
    note = page.get_by_text("Your cart is empty").inner_text()
    page.locator("#name").fill("Test Shopper")
    page.locator("#email").fill("shopper@example.com")
    page.locator("#card").fill("4242424242424242")
    page.get_by_role("button", name="Place order").click()
    confirmation = page.get_by_role("status").inner_text()
    print(f"R2 empty cart: page says {note!r}; after Place order {confirmation!r}")
    page.screenshot(path=str(OUT / "r2-empty-cart-order.jpg"), type="jpeg", quality=70)
    page.close()
    browser.close()
