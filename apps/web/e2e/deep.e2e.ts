import { expect, test, type Page } from "@playwright/test";

/**
 * Deep mode end to end on the demo shop, at $0 (run 9): the dashboard starts a deep run, the
 * worker crawls, the fake model (DEEP_SCRIPT, e2e/deep-script.ts) maps, plans, looks at every
 * viewport and reports two findings; verification confirms one by re-measuring it in a fresh
 * browser and keeps the other apart as unverified.
 */
async function signInAsDemoUser(page: Page) {
  await page.goto("/signin");
  await page.getByRole("button", { name: "Sign in as demo user" }).click();
  await page.waitForURL("**/dashboard");
}

test("a deep run on the demo shop: coverage, a verified finding and an unverified one apart", async ({ page }) => {
  await signInAsDemoUser(page);
  await page.getByRole("button", { name: /Use the demo shop/ }).click();
  await page.getByText("Deep test").click();
  await expect(page.getByLabel("Deep mode model")).toHaveValue("claude-sonnet-5-5");
  await page.getByRole("button", { name: "Start test" }).click();
  await page.waitForURL(/\/runs\/[0-9a-f-]{36}$/);
  await expect(page.getByTestId("engine-badge")).toHaveText(/Deep · Sonnet 5.5/);

  await expect(page.getByTestId("run-status")).toHaveText(/done/i, { timeout: 170_000 });
  await expect(page.getByTestId("coverage-summary")).toContainText("Finished");
  await expect(page.getByTestId("coverage-summary")).toContainText("10 of 10 plan items done");

  // Verified: on the report, with the other findings.
  await expect(page.getByTestId("bug-card").filter({ hasText: "E2E: the page title, re-measured" })).toBeVisible();
  // Unverified: kept apart, never among the bug cards.
  const unverified = page.getByTestId("unverified");
  await expect(unverified).toContainText("E2E: only in the agent's tab");
  await expect(page.getByTestId("bug-card").filter({ hasText: "only in the agent's tab" })).toHaveCount(0);
});
