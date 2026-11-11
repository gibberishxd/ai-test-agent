import { expect, test } from "@playwright/test";

/**
 * Run 4, J2: a workspace saves how to sign in to its app. The password goes in once and is never
 * shown again, on the page or in what the page loads. Uses the clean demo shop's address and
 * deletes the setup afterwards, so other tests' runs aren't signed in.
 */
test("save a sign-in setup: the password is never shown again", async ({ page }) => {
  const password = "e2e-Secret-Pass-9";
  const responses: string[] = [];
  page.on("response", async (response) => {
    if (response.url().includes("/api/login-setups") || response.url().includes("/settings")) {
      responses.push(await response.text().catch(() => ""));
    }
  });

  await page.goto("/signin");
  await page.getByRole("button", { name: "Sign in as demo user" }).click();
  await page.waitForURL("**/dashboard");
  await page.goto("/settings");

  await page.getByLabel("Site").fill("http://localhost:5174");
  await page.getByLabel("Login page").fill("http://localhost:5174/login");
  await page.getByLabel("Test account username or email").fill("demo@example.com");
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Save sign-in" }).click();

  const setup = page.getByTestId("login-setup-list").getByRole("listitem").filter({ hasText: "http://localhost:5174" });
  await expect(setup).toContainText("password saved");
  await expect(setup).toContainText("Not tested");
  await expect(page.getByLabel("Password", { exact: true })).toHaveValue("");
  expect(await page.content()).not.toContain(password);
  expect(responses.join("\n")).not.toContain(password);

  await setup.getByRole("button", { name: "Delete" }).click();
  await expect(setup).toHaveCount(0);
});
