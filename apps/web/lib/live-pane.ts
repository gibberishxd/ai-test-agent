/**
 * The live browser pane's logic, as pure functions so it is unit-tested without a browser.
 *
 * Each agent step stores a screenshot of the page *before* its action (what the agent looked
 * at when it chose), the box of the element it chose in screen pixels, and the screen size.
 * The pane draws the box over the screenshot. Percentages instead of pixels keep the outline
 * in place at any display size: the screenshot is shown scaled, the box scales with it.
 */
import type { StepView } from "@/lib/serialize";

export type Box = { x: number; y: number; width: number; height: number };
export type Viewport = { width: number; height: number };
export type OutlineStyle = { left: string; top: string; width: string; height: string };

const isNumber = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);

export function boxOf(step: StepView): Box | null {
  const box = step.args.box as Partial<Box> | null | undefined;
  if (!box || typeof box !== "object") return null;
  const { x, y, width, height } = box;
  return isNumber(x) && isNumber(y) && isNumber(width) && isNumber(height) ? { x, y, width, height } : null;
}

export function viewportOf(step: StepView): Viewport | null {
  const viewport = step.args.viewport as Partial<Viewport> | null | undefined;
  if (!viewport || typeof viewport !== "object") return null;
  const { width, height } = viewport;
  return isNumber(width) && isNumber(height) && width > 0 && height > 0 ? { width, height } : null;
}

const pct = (value: number) => `${Math.round(value * 10000) / 100}%`;

/**
 * Where to draw the outline, as CSS percentages of the screenshot. A box partly off the screen
 * is clipped to the visible part; a box entirely off it, empty or missing draws nothing.
 */
export function outlineStyle(box: Box | null, viewport: Viewport | null): OutlineStyle | null {
  if (!box || !viewport || box.width <= 0 || box.height <= 0) return null;
  const left = Math.max(box.x, 0);
  const top = Math.max(box.y, 0);
  const right = Math.min(box.x + box.width, viewport.width);
  const bottom = Math.min(box.y + box.height, viewport.height);
  if (right <= left || bottom <= top) return null;
  return {
    left: pct(left / viewport.width),
    top: pct(top / viewport.height),
    width: pct((right - left) / viewport.width),
    height: pct((bottom - top) / viewport.height),
  };
}

/** The steps the pane can show: those with a screenshot, oldest first. */
export function frames(steps: StepView[]): StepView[] {
  return steps.filter((step) => step.screenshot).sort((a, b) => a.index - b.index);
}

/** The frame to show: the one picked in the filmstrip, else the newest (following the run). */
export function currentFrame(steps: StepView[], picked: number | null): StepView | null {
  const all = frames(steps);
  return all.find((step) => step.index === picked) ?? all.at(-1) ?? null;
}
