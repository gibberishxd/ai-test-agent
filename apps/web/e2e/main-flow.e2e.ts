import { expect, test } from "@playwright/test";

/**
 * The demo, as a test: open the dashboard, start a run on the demo shop, wait for the worker
 * to finish it, and see bugs on the report.
 */
test("start a run from the dashboard and see bugs on the report", async ({ page }) => {
  // Signed in (dev demo user): visitors are limited to 5 runs per hour, and this test runs often.
  await page.goto("/signin");
  await page.getByRole("button", { name: "Sign in as demo user" }).click();
  await page.waitForURL("**/dashboard");
  await page.getByRole("button", { name: /Use the demo shop/ }).click();
  await expect(page.getByLabel("URL to test")).toHaveValue("http://localhost:5173");
  await page.getByText("Passive scan").click();
  await page.getByRole("button", { name: "Start test" }).click();

  // The live run page.
  await page.waitForURL(/\/runs\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("http://localhost:5173/"); // normalised URL

  // Steps appear while it runs, then the run finishes (polling every 1.5 s).
  await expect(page.getByTestId("run-status")).toHaveText(/done/i, { timeout: 150_000 });

  // The report: bug cards with evidence and export buttons.
  const bugs = page.getByTestId("bug-card");
  await expect(bugs.first()).toBeVisible();
  expect(await bugs.count()).toBeGreaterThanOrEqual(1);
  await expect(page.getByText("GET /api/profile fails with HTTP 500")).toBeVisible();
  await expect(bugs.first().getByRole("button", { name: "Copy as GitHub issue" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Download JSON" })).toBeVisible();
});

test("the form explains what's wrong with an invalid URL", async ({ page }) => {
  await page.goto("/dashboard");
  await page.getByLabel("URL to test").fill("not a url");
  await page.getByRole("button", { name: "Start test" }).click();
  await expect(page.getByText("That isn't a valid URL.")).toBeVisible();
});

test("interactive mode is refused on an unverified domain", async ({ page }) => {
  await page.goto("/dashboard");
  await page.getByLabel("URL to test").fill("https://example.com");
  await page.getByText("Interactive test").click();
  await page.getByRole("button", { name: "Start test" }).click();
  await expect(page.getByText(/only on the demo shop and on domains you've verified/)).toBeVisible();
});
