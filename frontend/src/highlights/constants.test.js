import { describe, it, expect } from "vitest";
import { HIGHLIGHT_COLORS, HIGHLIGHT_TINT } from "./constants";
import { SCHEMES } from "../theme/schemes";
import { contrast, mix } from "../theme/colors";

// Automatic-light and Automatic-dark use the stylesheet palettes; the others
// are the explicit schemes.
const THEMES = {
  autoLight: { bgs: ["#f7f3ea", "#ffffff"], text: "#2b2622" },
  autoDark: { bgs: ["#1c1a17", "#262320"], text: "#ece6d9" },
  light: { bgs: [SCHEMES.light.bg, SCHEMES.light.surface], text: SCHEMES.light.text },
  dark: { bgs: [SCHEMES.dark.bg, SCHEMES.dark.surface], text: SCHEMES.dark.text },
  contrast: { bgs: [SCHEMES.contrast.bg, SCHEMES.contrast.surface], text: SCHEMES.contrast.text },
};

describe("highlight colours", () => {
  it("six_named_colours", () => {
    expect(HIGHLIGHT_COLORS.map((c) => c.id)).toEqual(["yellow", "green", "blue", "pink", "orange", "purple"]);
    expect(HIGHLIGHT_COLORS.map((c) => c.label)).toEqual(["Yellow", "Green", "Blue", "Pink", "Orange", "Purple"]);
  });

  it("tint_is_within_the_allowed_range", () => {
    expect(HIGHLIGHT_TINT).toBeGreaterThanOrEqual(0.2);
    expect(HIGHLIGHT_TINT).toBeLessThanOrEqual(0.35);
  });

  it("every_colour_keeps_text_at_aa_in_every_theme", () => {
    for (const [name, t] of Object.entries(THEMES)) {
      for (const bg of t.bgs) {
        for (const c of HIGHLIGHT_COLORS) {
          const tinted = mix(bg, c.hue, HIGHLIGHT_TINT);
          expect(contrast(t.text, tinted), `${name} ${c.id} on ${bg}`).toBeGreaterThanOrEqual(4.5);
        }
      }
    }
  });
});
