import { describe, expect, it } from "vitest";
import { boxOf, currentFrame, frames, outlineStyle, viewportOf } from "./live-pane";
import type { StepView } from "./serialize";

const VIEWPORT = { width: 1280, height: 800 };

function step(index: number, fields: Partial<StepView> = {}): StepView {
  return {
    index,
    action: "click",
    args: {},
    reasoning: null,
    url: "http://localhost:5173/",
    screenshot: `run/agent-${index}.png`,
    events: [],
    blocked: false,
    blockReason: null,
    costUsd: 0,
    createdAt: "2026-11-10T10:00:00.000Z",
    ...fields,
  };
}

describe("outlineStyle", () => {
  it("scales a box in screen pixels to percentages of the screenshot", () => {
    expect(outlineStyle({ x: 640, y: 200, width: 128, height: 40 }, VIEWPORT)).toEqual({
      left: "50%",
      top: "25%",
      width: "10%",
      height: "5%",
    });
  });

  it("works for the phone viewport too", () => {
    const style = outlineStyle({ x: 0, y: 406, width: 375, height: 81.2 }, { width: 375, height: 812 });
    expect(style).toEqual({ left: "0%", top: "50%", width: "100%", height: "10%" });
  });

  it("clips a box that is partly off the screen to the visible part", () => {
    expect(outlineStyle({ x: -64, y: 760, width: 128, height: 80 }, VIEWPORT)).toEqual({
      left: "0%",
      top: "95%",
      width: "5%",
      height: "5%",
    });
  });

  it("draws nothing for a box that is off the screen, empty or missing", () => {
    expect(outlineStyle({ x: 10, y: -300, width: 100, height: 40 }, VIEWPORT)).toBeNull();
    expect(outlineStyle({ x: 10, y: 10, width: 0, height: 40 }, VIEWPORT)).toBeNull();
    expect(outlineStyle(null, VIEWPORT)).toBeNull();
    expect(outlineStyle({ x: 1, y: 1, width: 1, height: 1 }, null)).toBeNull();
  });
});

describe("reading boxes from steps", () => {
  it("takes the box and viewport the worker stored in the step's args", () => {
    const s = step(1, { args: { box: { x: 1, y: 2, width: 3, height: 4 }, viewport: VIEWPORT } });
    expect(boxOf(s)).toEqual({ x: 1, y: 2, width: 3, height: 4 });
    expect(viewportOf(s)).toEqual(VIEWPORT);
  });

  it("ignores malformed values instead of drawing them", () => {
    const s = step(1, { args: { box: { x: "1", y: 2 }, viewport: "big" } });
    expect(boxOf(s)).toBeNull();
    expect(viewportOf(s)).toBeNull();
  });
});

describe("frames", () => {
  const steps = [step(0, { action: "visit" }), step(1, { screenshot: null }), step(2), step(3)];

  it("are the steps that have a screenshot, oldest first", () => {
    expect(frames(steps).map((s) => s.index)).toEqual([0, 2, 3]);
  });

  it("the pane follows the newest frame unless one was picked", () => {
    expect(currentFrame(steps, null)?.index).toBe(3);
    expect(currentFrame(steps, 2)?.index).toBe(2);
    expect(currentFrame(steps, 99)?.index).toBe(3); // a pick that no longer exists
    expect(currentFrame([], null)).toBeNull();
  });
});
