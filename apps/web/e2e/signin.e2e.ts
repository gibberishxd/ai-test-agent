import { expect, test } from "@playwright/test";

/**
 * "Sign in as demo user" used to land back on /signin now and then (about 1 in 20 tries).
 * Cause: Auth.js mints a new CSRF cookie for every auth request that arrives without one, and
 * the page fired its own /api/auth/session requests on load (SessionProvider). When one of
 * those answered after the button's /api/auth/csrf, it replaced the cookie, the posted token
 * no longer matched, and Auth.js sent the browser back to sign-in. So: nothing may call the
 * auth API on the sign-in page before the user clicks.
 */
test("the sign-in page makes no auth requests of its own before the click", async ({ page }) => {
  const early: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/auth/")) early.push(new URL(request.url()).pathname);
  });
  await page.goto("/signin");
  await page.getByRole("button", { name: "Sign in as demo user" }).waitFor();
  await page.waitForLoadState("networkidle");
  // Focus and visibility changes used to refetch the session too.
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await page.waitForTimeout(500);
  expect(early).toEqual([]);
});

test("signing in as the demo user reaches the dashboard every time", async ({ browser }) => {
  for (let attempt = 0; attempt < 10; attempt++) {
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto("/signin");
    await page.getByRole("button", { name: "Sign in as demo user" }).click();
    await page.waitForURL("**/dashboard", { timeout: 15_000 });
    await context.close();
  }
});
