import { describe, it, expect } from "vitest";
import { parseHex, luminance, contrast, mix, readableOn } from "./colors";
import { mulberry32 } from "../breaks/rng";

describe("colors", () => {
  it("parse_hex_accepts_and_normalises", () => {
    expect(parseHex("#ABC")).toBe("#aabbcc");
    expect(parseHex(" #A8562F ")).toBe("#a8562f");
  });
  it("parse_hex_rejects_junk", () => {
    for (const j of ["red", "#12", "#12345", "#1234567", "#gggggg", "", null, 42, "#aabbccdd"])
      expect(parseHex(j)).toBeNull();
  });
  it("contrast_known_values", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 0);
    expect(contrast("#336699", "#336699")).toBeCloseTo(1, 5);
    expect(contrast("#112233", "#ddeeff")).toBeCloseTo(contrast("#ddeeff", "#112233"), 8);
  });
  it("luminance_extremes", () => {
    expect(luminance("#000000")).toBe(0);
    expect(luminance("#ffffff")).toBeCloseTo(1, 5);
  });
  it("mix_endpoints_and_midpoint", () => {
    expect(mix("#102030", "#ffffff", 0)).toBe("#102030");
    expect(mix("#102030", "#ffffff", 1)).toBe("#ffffff");
    expect(["#808080", "#7f7f7f"]).toContain(mix("#000000", "#ffffff", 0.5));
    expect(mix("#000000", "#ffffff", -3)).toBe("#000000");
    expect(mix("#000000", "#ffffff", 9)).toBe("#ffffff");
  });
  it("readable_on", () => {
    expect(readableOn("#000000")).toBe("#ffffff");
    expect(readableOn("#1a2b6d")).toBe("#ffffff");
    expect(readableOn("#ffffff")).toBe("#000000");
    expect(readableOn("#ffff00")).toBe("#000000");
    const r = mulberry32(7);
    for (let i = 0; i < 200; i++) {
      const c = "#" + [r(), r(), r()].map((x) => Math.floor(x * 256).toString(16).padStart(2, "0")).join("");
      expect(contrast(readableOn(c), c)).toBeGreaterThanOrEqual(4.5);
    }
  });
});
