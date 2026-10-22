import { describe, expect, it } from "vitest";
import { EDGE_MARGIN, MAX_STEP, edgeScrollStep, usableBottom } from "./selectionScroll";

const VIEWPORT = 800;

describe("usableBottom", () => {
  it("is the bottom of the window when no bar is open", () => {
    expect(usableBottom(VIEWPORT, 0)).toBe(800);
    expect(usableBottom(VIEWPORT)).toBe(800);
  });

  it("is the top of the bar when one is open", () => {
    expect(usableBottom(VIEWPORT, 260)).toBe(540);
  });

  it("never goes negative, however tall the bar is", () => {
    expect(usableBottom(400, 900)).toBe(0);
  });

  it("ignores nonsense measurements rather than propagating NaN", () => {
    expect(usableBottom(VIEWPORT, NaN)).toBe(800);
    expect(usableBottom(VIEWPORT, -50)).toBe(800);
    expect(usableBottom(undefined)).toBe(0);
  });
});

describe("edgeScrollStep", () => {
  const bottom = usableBottom(VIEWPORT, 260); // 540

  it("holds still in the middle of the usable area", () => {
    expect(edgeScrollStep(300, { bottom })).toBe(0);
    expect(edgeScrollStep(bottom - EDGE_MARGIN - 1, { bottom })).toBe(0);
  });

  it("starts scrolling down as the pointer nears the top of the bar", () => {
    const step = edgeScrollStep(bottom - EDGE_MARGIN + 1, { bottom });
    expect(step).toBeGreaterThan(0);
    expect(step).toBeLessThan(MAX_STEP);
  });

  it("goes faster the closer the pointer gets", () => {
    const near = edgeScrollStep(bottom - EDGE_MARGIN + 10, { bottom });
    const nearer = edgeScrollStep(bottom - 5, { bottom });
    expect(nearer).toBeGreaterThan(near);
  });

  it("runs at full speed once the pointer is over the bar", () => {
    // The gesture someone makes when they want to keep going. It must not
    // stall just because the pointer left the usable area.
    expect(edgeScrollStep(bottom + 1, { bottom })).toBe(MAX_STEP);
    expect(edgeScrollStep(VIEWPORT, { bottom })).toBe(MAX_STEP);
    expect(edgeScrollStep(VIEWPORT + 200, { bottom })).toBe(MAX_STEP);
  });

  it("scrolls up near the top of the window", () => {
    // Full speed only once the pointer is at or past the edge itself; just
    // inside it the ramp is still climbing.
    expect(edgeScrollStep(0, { bottom })).toBe(-MAX_STEP);
    expect(edgeScrollStep(-20, { bottom })).toBe(-MAX_STEP);
    expect(edgeScrollStep(5, { bottom })).toBeLessThan(0);
    expect(edgeScrollStep(5, { bottom })).toBeGreaterThan(-MAX_STEP);
    expect(edgeScrollStep(EDGE_MARGIN - 10, { bottom })).toBeLessThan(0);
    expect(edgeScrollStep(EDGE_MARGIN + 1, { bottom })).toBe(0);
  });

  it("respects a top offset, for a reader with a sticky top bar", () => {
    expect(edgeScrollStep(70, { top: 60, bottom })).toBeLessThan(0);
    expect(edgeScrollStep(70, { top: 0, bottom })).toBe(0);
  });

  it("does nothing when the usable area is too small to have two edges", () => {
    // A bar taller than the window would otherwise scroll in both directions
    // at once, whichever way the pointer moved.
    expect(edgeScrollStep(10, { bottom: 20 })).toBe(0);
    expect(edgeScrollStep(10, { bottom: 0 })).toBe(0);
  });

  it("returns 0 rather than NaN for missing measurements", () => {
    expect(edgeScrollStep(NaN, { bottom })).toBe(0);
    expect(edgeScrollStep(100, {})).toBe(0);
    expect(edgeScrollStep(100)).toBe(0);
  });

  it("always returns a whole number of pixels", () => {
    for (let y = 0; y <= VIEWPORT; y += 7) {
      expect(Number.isInteger(edgeScrollStep(y, { bottom }))).toBe(true);
    }
  });
});
