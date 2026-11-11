#!/usr/bin/env node
/**
 * Run AI Test Agent from CI: start a run, wait for it, print a summary, write JUnit XML, and
 * exit non-zero when a bug at or above a chosen severity was found.
 *
 * Needs Node 20+ (built-in fetch), no packages. Environment:
 *   ATA_API_URL   the app's address, e.g. https://ata.example.com
 *   ATA_API_KEY   a workspace API key (Settings → CI integration), kept in your CI's secrets
 *
 * Usage:
 *   node ata-run.mjs <target-url> [--mode passive|interactive] [--fail-on critical|high|medium|low|none]
 *                    [--junit report.xml] [--timeout-minutes 30] [--max-steps N] [--max-minutes N]
 *                    [--focus "checkout"]
 *
 * Exit codes: 0 no bug at or above --fail-on · 1 bugs found · 2 the run failed or timed out ·
 * 3 bad usage or the API refused the request.
 */
import { writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";

const SEVERITIES = ["critical", "high", "medium", "low"];
const POLL_SECONDS = 10;

export function parseArgs(argv) {
  const options = {
    targetUrl: null,
    mode: "passive",
    failOn: "high",
    junit: null,
    timeoutMinutes: 30,
    maxSteps: null,
    maxMinutes: null,
    focus: null,
  };
  const flags = {
    "--mode": (v) => (options.mode = v),
    "--fail-on": (v) => (options.failOn = v),
    "--junit": (v) => (options.junit = v),
    "--timeout-minutes": (v) => (options.timeoutMinutes = Number(v)),
    "--max-steps": (v) => (options.maxSteps = Number(v)),
    "--max-minutes": (v) => (options.maxMinutes = Number(v)),
    "--focus": (v) => (options.focus = v),
  };
  for (let i = 0; i < argv.length; i++) {
    if (flags[argv[i]]) flags[argv[i]](argv[++i]);
    else if (!options.targetUrl) options.targetUrl = argv[i];
    else throw new Error(`unknown argument: ${argv[i]}`);
  }
  return options;
}

/** True when the counts include a bug at `threshold` severity or worse ("none": never). */
export function failsAt(counts, threshold) {
  if (threshold === "none") return false;
  const worstAllowed = SEVERITIES.indexOf(threshold);
  if (worstAllowed < 0) throw new Error(`--fail-on must be one of ${SEVERITIES.join(", ")}, none`);
  return SEVERITIES.slice(0, worstAllowed + 1).some((severity) => (counts[severity] ?? 0) > 0);
}

export function summarize(report) {
  const { run, counts, bugs } = report;
  const tally = SEVERITIES.filter((s) => counts[s]).map((s) => `${counts[s]} ${s}`).join(", ") || "no bugs";
  const sorted = [...bugs].sort((a, b) => SEVERITIES.indexOf(a.severity) - SEVERITIES.indexOf(b.severity));
  return [
    `AI Test Agent: ${run.target_url} · ${run.status} in ${run.duration_s ?? "?"} s · ${tally}`,
    ...sorted.map((bug) => `  [${bug.severity}] ${bug.title} (${bug.page_url})`),
    `Full report: ${run.links.dashboard}`,
  ].join("\n");
}

async function api(path, init = {}) {
  const base = process.env.ATA_API_URL?.replace(/\/$/, "");
  const key = process.env.ATA_API_KEY;
  if (!base || !key) throw Object.assign(new Error("set ATA_API_URL and ATA_API_KEY"), { exit: 3 });
  for (let attempt = 0; ; attempt++) {
    const response = await fetch(`${base}/api/v1${path}`, {
      ...init,
      headers: { authorization: `Bearer ${key}`, "content-type": "application/json", ...(init.headers ?? {}) },
    });
    if (response.status === 429 && attempt < 5) {
      const wait = Number(response.headers.get("retry-after") ?? POLL_SECONDS);
      await new Promise((resolve) => setTimeout(resolve, wait * 1000));
      continue;
    }
    if (!response.ok) {
      const detail = await response.text();
      throw Object.assign(new Error(`API ${response.status}: ${detail}`), { exit: 3 });
    }
    return response;
  }
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (!options.targetUrl) throw Object.assign(new Error("usage: ata-run.mjs <target-url> [options]"), { exit: 3 });
  const started = await (
    await api("/runs", {
      method: "POST",
      body: JSON.stringify({
        target_url: options.targetUrl,
        mode: options.mode,
        focus: options.focus,
        ...(options.maxSteps ? { max_steps: options.maxSteps } : {}),
        ...(options.maxMinutes ? { max_minutes: options.maxMinutes } : {}),
      }),
    })
  ).json();
  console.log(`Started run ${started.id}: ${started.links.dashboard}`);

  const deadline = Date.now() + options.timeoutMinutes * 60_000;
  let status = started;
  while (!status.finished) {
    if (Date.now() > deadline) throw Object.assign(new Error(`run ${started.id} didn't finish in time`), { exit: 2 });
    await new Promise((resolve) => setTimeout(resolve, POLL_SECONDS * 1000));
    status = await (await api(`/runs/${started.id}`)).json();
  }
  const report = await (await api(`/runs/${started.id}/report`)).json();
  console.log(summarize(report));
  if (options.junit) {
    await writeFile(options.junit, await (await api(`/runs/${started.id}/report?format=junit`)).text());
    console.log(`JUnit report: ${options.junit}`);
  }
  if (status.status !== "done") return 2;
  return failsAt(report.counts, options.failOn) ? 1 : 0;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main()
    .then((code) => process.exit(code))
    .catch((error) => {
      console.error(error.message);
      process.exit(error.exit ?? 2);
    });
}
