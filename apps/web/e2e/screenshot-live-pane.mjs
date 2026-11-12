// Takes docs/screenshots/live-pane.png from the newest interactive run of the demo user.
// Not a test: run by hand with `node e2e/screenshot-live-pane.mjs` while the app is running.
import { chromium } from "@playwright/test";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
await page.goto("http://localhost:3000/signin");
await page.getByRole("button", { name: "Sign in as demo user" }).click();
await page.waitForURL("**/dashboard");
await page.goto("http://localhost:3000/runs");
await page.getByRole("link", { name: /localhost:5173/ }).first().click();
await page.waitForURL(/\/runs\/[0-9a-f-]{36}$/);
const pane = page.getByTestId("live-pane");
await pane.getByRole("button", { name: /: Clicked / }).first().click();
await page.getByTestId("live-pane-outline").waitFor();
await pane.screenshot({ path: "../../docs/screenshots/live-pane.png" });
await browser.close();
console.log("saved docs/screenshots/live-pane.png");
