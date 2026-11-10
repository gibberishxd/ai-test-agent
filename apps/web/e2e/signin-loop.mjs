// Signs in as the demo user N times in fresh browsers and counts how often it doesn't reach
// the dashboard. Not a test: run by hand while the app runs, e.g.
//   node e2e/signin-loop.mjs 50            (one at a time)
//   node e2e/signin-loop.mjs 50 4          (4 browsers at once)
// Prints each failure's final URL, then "N failed of M".
import { chromium } from "@playwright/test";

const total = Number(process.argv[2] ?? 50);
const parallel = Number(process.argv[3] ?? 1);
const base = process.env.BASE_URL ?? "http://localhost:3000";

const browser = await chromium.launch();
let failed = 0;
let started = 0;

async function once(n) {
  const context = await browser.newContext();
  const page = await context.newPage();
  const auth = []; // what the auth endpoints answered, printed when the attempt fails
  page.on("response", (r) => {
    if (r.url().includes("/api/auth/")) auth.push(`${r.request().method()} ${new URL(r.url()).pathname} → ${r.status()}`);
  });
  page.on("framenavigated", (f) => f === page.mainFrame() && auth.push(`navigated: ${f.url()}`));
  try {
    await page.goto(`${base}/signin`);
    await page.getByRole("button", { name: "Sign in as demo user" }).click();
    await page.waitForURL("**/dashboard", { timeout: 15_000 });
  } catch {
    failed += 1;
    console.log(`#${n} failed: ended on ${page.url()}\n   ${auth.join("\n   ")}`);
  } finally {
    await context.close();
  }
}

async function lane() {
  while (started < total) await once(++started);
}

await Promise.all(Array.from({ length: parallel }, lane));
await browser.close();
console.log(`${failed} failed of ${total}`);
process.exit(failed ? 1 : 0);
