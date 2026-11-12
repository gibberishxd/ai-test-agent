import { expect, test, type Page } from "@playwright/test";

/**
 * One test per planted bug of the holdout app (ids from bugs.json). Each measures whether the
 * bug shows, then expects: shows on the "buggy" project, doesn't show on the "clean" project.
 */
const expectBug = (shows: boolean) => expect(shows).toBe(test.info().project.name === "buggy");

async function fillBooking(page: Page, checkIn: string, checkOut: string) {
  await page.goto("/rooms/1");
  await page.getByLabel("Guest name").fill("Test User");
  await page.getByLabel("Email").fill("test@example.com");
  await page.getByLabel("Check-in").fill(checkIn);
  await page.getByLabel("Check-out").fill(checkOut);
}

test("bug 1: availability API answers 503", async ({ page }) => {
  const response = page.waitForResponse("**/api/availability?room=1");
  await page.goto("/rooms/1");
  expectBug((await response).status() === 503);
});

test("bug 2: phone field has no label", async ({ page }) => {
  await page.goto("/rooms/1");
  const phone = page.locator('input[name="phone"]');
  const named = await phone.evaluate(
    (el) => (el as HTMLInputElement).labels!.length > 0 || el.hasAttribute("aria-label"),
  );
  expectBug(!named);
});

test("bug 3: total ignores the number of nights", async ({ page }) => {
  await fillBooking(page, "2027-02-01", "2027-02-04"); // 3 nights × $120
  expectBug((await page.getByTestId("total").textContent()) !== "$360.00");
});

test("bug 4: check-out before check-in is accepted", async ({ page }) => {
  await fillBooking(page, "2027-02-04", "2027-02-01");
  await page.getByRole("button", { name: "Book now" }).click();
  // Wait for either outcome: a confirmation (bug) or an error under a field (correct).
  await page.locator("[role=status], .field-error").first().waitFor();
  const confirmed = await page.getByRole("status").filter({ hasText: "Booked!" }).count();
  expectBug(confirmed > 0);
});

test("bug 5: double-clicking Book now books twice", async ({ page }) => {
  await fillBooking(page, "2027-02-01", "2027-02-03");
  await page.getByRole("button", { name: "Book now" }).dblclick();
  await page.getByRole("link", { name: "My bookings" }).first().click();
  await page.getByRole("heading", { name: "My bookings" }).waitFor();
  await page.getByTestId("bookings").locator("li").first().waitFor();
  const count = await page.getByTestId("bookings").locator("li").count();
  expectBug(count === 2);
});

test("bug 6: long room name runs off a phone screen", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/rooms/3");
  const title = page.locator("h1.room-title");
  const overflows = await title.evaluate((el) => el.scrollWidth > el.clientWidth);
  expectBug(overflows);
});

// Not planted: a real bug the agent found in the clean build (run 3, H7), now fixed. The buggy
// build shows no date error at all (bug 4), so only the clean build is checked.
test("fixed: a date error goes away once the date is corrected", async ({ page }) => {
  test.skip(test.info().project.name === "buggy", "bug 4 hides it");
  await fillBooking(page, "2027-02-04", "2027-02-01");
  await page.getByRole("button", { name: "Book now" }).click();
  const error = page.getByText("Check-out must be after check-in.");
  await expect(error).toBeVisible();
  await page.getByLabel("Check-out").fill("2027-02-06");
  await expect(error).toBeHidden();
});
