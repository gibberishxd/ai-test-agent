// Fresh screenshots of the main screens for the README (run 5, K5). Not a test: run by hand
// with `node e2e/screenshots.mjs` while the web app runs (npm run dev) and the e2e tests have
// left runs in the demo user's workspace. Writes docs/screenshots/*.png.
import { chromium } from "@playwright/test";

const BASE = process.env.BASE_URL ?? "http://localhost:3000";
const OUT = "../../docs/screenshots";
const browser = await chromium.launch();
// Each part signs in as someone else: a fresh context (cookies) per part.
async function freshPage() {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  context.setDefaultTimeout(120_000);
  return context.newPage();
}

async function shot(page, name, locator) {
  await page.waitForLoadState("networkidle");
  const path = `${OUT}/${name}.png`;
  if (locator) await locator.screenshot({ path });
  else await page.screenshot({ path, fullPage: false });
  console.log(`saved docs/screenshots/${name}.png`);
}

// 1. A new team's first look: Getting started.
{
  const page = await freshPage();
  await page.goto(`${BASE}/signin`, { waitUntil: "networkidle" });
  await page.getByLabel("Or create a test account").fill(`screens-${Date.now()}@company.test`);
  await page.getByRole("button", { name: "Create test account" }).click();
  await page.waitForURL("**/dashboard");
  await shot(page, "getting-started");
  await page.close();
}

// 2. The demo user's workspace: a report, the live pane, usage.
{
  const page = await freshPage();
  await page.goto(`${BASE}/signin`, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "Sign in as demo user" }).click();
  await page.waitForURL("**/dashboard");
  await shot(page, "dashboard");

  await page.goto(`${BASE}/runs`);
  await page.getByRole("link", { name: /localhost:5173/ }).first().click();
  await page.waitForURL(/\/runs\/[0-9a-f-]{36}$/);
  await page.getByTestId("bug-card").first().waitFor();
  await shot(page, "report");
  const pane = page.getByTestId("live-pane");
  const clicked = pane.getByRole("button", { name: /: Clicked / }).first();
  if (await clicked.count()) {
    await clicked.click();
    await page.getByTestId("live-pane-outline").waitFor();
    await shot(page, "live-pane", pane);
  }

  await page.goto(`${BASE}/settings/usage`);
  await shot(page, "usage");
  await page.goto(`${BASE}/benchmark`);
  await shot(page, "benchmark");
  await page.close();
}

await browser.close();
