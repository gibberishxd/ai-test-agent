/**
 * The OpenAPI spec is the contract CI scripts are written against (run 4, J3). These tests keep
 * code and spec in step: every /api/v1 route is in the spec with exactly its methods, and what
 * the handlers' helpers return validates against the spec's schemas.
 */
import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import Ajv2020 from "ajv/dist/2020";
import { describe, expect, it } from "vitest";
import { apiReport, apiStatus } from "./api-v1";

const spec = JSON.parse(readFileSync(join(__dirname, "..", "openapi.json"), "utf8"));
const V1 = join(__dirname, "..", "app", "api", "v1");
const METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"];

function routeFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) =>
    entry.isDirectory() ? routeFiles(join(dir, entry.name)) : entry.name === "route.ts" ? [join(dir, entry.name)] : [],
  );
}

/** app/api/v1/runs/[id]/report/route.ts → /runs/{id}/report, with its exported methods. */
function routes(): Record<string, string[]> {
  return Object.fromEntries(
    routeFiles(V1)
      .map((file) => {
        const path = "/" + relative(V1, file).replace(/\/?route\.ts$/, "").replace(/\[(\w+)\]/g, "{$1}");
        const source = readFileSync(file, "utf8");
        const methods = METHODS.filter((m) => new RegExp(`export async function ${m}\\b`).test(source)).map((m) => m.toLowerCase());
        return [path, methods] as const;
      })
      .filter(([path]) => path !== "/openapi.json"),
  );
}

describe("openapi.json", () => {
  it("documents every /api/v1 route with exactly the methods it has", () => {
    const documented = Object.fromEntries(Object.entries(spec.paths as Record<string, object>).map(([path, ops]) => [path, Object.keys(ops).sort()]));
    const implemented = Object.fromEntries(Object.entries(routes()).map(([path, methods]) => [path, [...methods].sort()]));
    expect(implemented).toEqual(documented);
  });

  const ajv = new Ajv2020({ strict: false });
  ajv.addSchema(spec, "openapi");
  const valid = (schema: string, value: unknown) => {
    const validate = ajv.getSchema(`openapi#/components/schemas/${schema}`)!;
    const ok = validate(value);
    return ok ? true : validate.errors;
  };

  const run = {
    id: "11111111-2222-3333-4444-555555555555",
    targetUrl: "https://staging.example.com/",
    mode: "passive",
    status: "done",
    costUsd: 0,
    pagesVisited: 3,
    createdAt: new Date(),
    startedAt: new Date(),
    finishedAt: new Date(),
    bugs: [
      { id: "b", title: "t", severity: "high", category: "network", pageUrl: "https://x/", status: "confirmed", source: "deterministic", expected: null, actual: "500", reproSteps: ["Open https://x/"] },
    ],
  };

  it("a run status validates against RunStatus", () => {
    expect(valid("RunStatus", apiStatus(run, "https://app.test"))).toBe(true);
    expect(valid("RunStatus", apiStatus({ ...run, status: "queued", startedAt: null, finishedAt: null }, ""))).toBe(true);
  });

  it("a report validates against Report", () => {
    expect(valid("Report", apiReport(run, "https://app.test"))).toBe(true);
  });
});
