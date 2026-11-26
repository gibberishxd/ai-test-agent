/**
 * The fake model's turns for deep runs in the end-to-end tests (DEEP_SCRIPT, run 9): map, plan,
 * screenshots at every viewport, two findings (one re-measured and confirmed in a fresh
 * browser, one that only holds in the agent's own tab, so it stays unverified), every item
 * ticked, finish. Generic: it checks the page has a title, nothing specific to the demo shop.
 */
const AREAS = ["flows", "navigation", "visual", "accessibility", "meta", "console_network", "promises"];
const VIEWPORTS: [number, number][] = [
  [390, 844],
  [768, 1024],
  [1440, 900],
];

const items = [
  ...AREAS.map((area) => ({ id: `${area}-1`, area, description: `check ${area}` })),
  ...VIEWPORTS.map(([w, h]) => ({ id: `layout-${w}`, area: "layout", viewport: `${w}x${h}`, description: "layout" })),
];

const looks = VIEWPORTS.flatMap(([width, height]) => [
  ["set_viewport", { width, height }],
  ["screenshot", {}],
]); // steps 4–9

export const DEEP_SCRIPT = JSON.stringify([
  [
    ["snapshot", {}], // 1
    ["save_map", { pages: [{ url: "/", purpose: "the start page" }], flows: [{ name: "browse", description: "open the start page" }], summary: "an app" }], // 2
  ],
  [["save_plan", { items }]], // 3
  [
    ...looks,
    ["flag_candidate", { title: "Title", observation: "the page title" }], // 10
    ["visible_text", {}], // 11
    ["report_bug", { candidate_id: "c1", title: "E2E: the page title, re-measured", severity: "low", category: "content", expected: "-", actual: "-", self_review: "measured", verify: { kind: "measure", snippet: "return document.title.length > 0", setup_steps: [], observed_value: true } }], // 12
    ["evaluate_js", { snippet: "window.__e2e = [1]; return 1" }], // 13
    ["flag_candidate", { title: "Tab state", observation: "only in this tab" }], // 14
    ["screenshot", {}], // 15
    ["report_bug", { candidate_id: "c2", title: "E2E: only in the agent's tab", severity: "low", category: "other", expected: "-", actual: "-", self_review: "checked", verify: { kind: "measure", snippet: "return window.__e2e.length", setup_steps: [], observed_value: 1 } }], // 16
    ...items.map((item) => ["tick", { item_id: item.id, status: "done", note: "ok" }]),
  ],
  [["finish", { summary: "e2e" }]],
]);
