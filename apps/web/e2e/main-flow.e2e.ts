import { expect, test, type Page } from "@playwright/test";

/** Sign in with the dev-only demo account (no retry: the old flake is fixed, see signin.e2e.ts). */
async function signInAsDemoUser(page: Page) {
  await page.goto("/signin");
  await page.getByRole("button", { name: "Sign in as demo user" }).click();
  await page.waitForURL("**/dashboard");
}

/**
 * The demo, as a test: open the dashboard, start a run on the demo shop, wait for the worker
 * to finish it, and see bugs on the report.
 */
test("start a run from the dashboard and see bugs on the report", async ({ page }) => {
  // Signed in (dev demo user): visitors are limited to 5 runs per hour, and this test runs often.
  await signInAsDemoUser(page);
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

test("the live browser pane shows the agent's screen and outlines what it clicks", async ({ page }) => {
  await signInAsDemoUser(page);
  await page.getByRole("button", { name: /Use the demo shop/ }).click();
  await page.getByText("Interactive test").click();
  await page.getByRole("button", { name: "Start test" }).click();
  await page.waitForURL(/\/runs\/[0-9a-f-]{36}$/);

  // During the run: the pane shows a screenshot as soon as the first page is visited.
  const pane = page.getByTestId("live-pane");
  await expect(pane.getByRole("img").first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId("live-pane-counter")).toHaveText(/Step \d+ of \d+/);

  // The scripted agent clicks the first element: picking that step outlines it.
  await expect(page.getByTestId("run-status")).toHaveText(/done/i, { timeout: 150_000 });
  await pane.getByRole("button", { name: /: Clicked / }).click();
  const outline = page.getByTestId("live-pane-outline");
  await expect(outline).toBeVisible();
  const box = await outline.boundingBox();
  expect(box!.width).toBeGreaterThan(2);
  expect(box!.height).toBeGreaterThan(2);
  await expect(pane.getByText(/^Clicked /)).toBeVisible();
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

test("a workspace model is stored with its key hidden and can't run until tested", async ({ page }) => {
  await signInAsDemoUser(page);
  await page.goto("/settings");

  const name = `E2E model ${Date.now()}`;
  await page.getByLabel("Name", { exact: true }).fill(name);
  await page.getByLabel("Base URL", { exact: true }).fill("https://api.example.test/v1");
  await page.getByLabel("Model", { exact: true }).fill("e2e-model");
  await page.getByLabel("API key", { exact: true }).fill("sk-e2e-secret-7391");
  await page.getByRole("button", { name: "Add model" }).click();

  const item = page.getByTestId("model-list").locator("li").filter({ hasText: name });
  await expect(item).toContainText("•••• 7391");
  await expect(item).toContainText("Not tested");
  await expect(page.getByText("sk-e2e-secret-7391")).toHaveCount(0);
  expect(await page.content()).not.toContain("sk-e2e-secret-7391");

  // The run form offers it, but not before it has passed Test connection.
  await page.goto("/dashboard");
  const option = page.getByRole("option", { name: new RegExp(name) });
  await expect(option).toBeDisabled();

  // Clean up so the dashboard stays tidy across runs.
  await page.goto("/settings");
  await item.getByRole("button", { name: "Delete" }).click();
  await expect(item).toHaveCount(0);
});
