import { expect, test } from "@playwright/test";

/**
 * Run 5, K5: a new team gets from sign-up to its first report without help. A fresh account
 * (the dev-only test sign-up, standing in for an email link) sees Getting started, finds where to
 * verify a domain, starts an interactive run on the demo shop, watches the live pane and reads
 * the report; then Getting started is done and goes away.
 */
test("a new team: sign up, get started, first run, live pane, report", async ({ page }) => {
  const email = `team-${Date.now()}@company.test`;
  await page.goto("/signin");
  await page.getByLabel("Or create a test account").fill(email);
  await page.getByRole("button", { name: "Create test account" }).click();
  await page.waitForURL("**/dashboard");

  // A brand-new workspace: the way to the first report, and what to do next.
  const steps = page.getByTestId("getting-started");
  await expect(steps).toContainText("1 of 5 done");
  await expect(steps).toContainText("Next: choose what to test");
  await steps.getByRole("link", { name: "Choose what to test" }).click();
  await expect(page.locator("#domains")).toContainText("Domains for interactive tests");
  await page.goto("/dashboard");

  // The first run: the demo shop, interactive, the server's model.
  await page.getByRole("button", { name: /Use the demo shop/ }).click();
  await page.getByText("Interactive test").click();
  await page.getByRole("button", { name: "Start test" }).click();
  await page.waitForURL(/\/runs\/[0-9a-f-]{36}$/);

  // Live: the agent's screen appears while it works.
  await expect(page.getByTestId("live-pane").getByRole("img").first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId("run-status")).toHaveText(/done/i, { timeout: 150_000 });

  // The report: findings with evidence.
  await expect(page.getByTestId("bug-card").first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Download JSON" })).toBeVisible();

  // Back on the dashboard, Getting started is finished and out of the way.
  await page.goto("/dashboard");
  await expect(page.getByTestId("getting-started")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Recent runs" })).toBeVisible();
});
