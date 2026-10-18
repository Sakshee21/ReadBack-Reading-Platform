import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { contrast } from "./colors";
import { mulberry32 } from "../breaks/rng";
import {
  SCHEME_IDS, VAR_MAP, SCHEMES, DEFAULT_PALETTE, derivePalette, checkPalette, schemePalette,
} from "./schemes";

const hexOf = (r) => "#" + [r(), r(), r()].map((x) => Math.floor(x * 256).toString(16).padStart(2, "0")).join("");
const greys = Array.from({ length: 256 }, (_, v) => "#" + v.toString(16).padStart(2, "0").repeat(3));

describe("schemes", () => {
  it("built_in_schemes_meet_aa", () => {
    for (const id of ["light", "dark", "contrast"]) {
      const p = SCHEMES[id];
      for (const k of Object.keys(VAR_MAP)) expect(p[k], `${id}.${k}`).toBeTruthy();
      for (const bg of [p.bg, p.surface]) {
        expect(contrast(p.text, bg), `${id} text`).toBeGreaterThanOrEqual(4.5);
        expect(contrast(p.textMuted, bg), `${id} muted`).toBeGreaterThanOrEqual(4.5);
      }
      expect(contrast(p.onAccent, p.accent), `${id} onAccent`).toBeGreaterThanOrEqual(4.5);
      expect(contrast(p.accent, p.bg), `${id} accent`).toBeGreaterThanOrEqual(3);
      expect(contrast(p.danger, p.surface), `${id} danger`).toBeGreaterThanOrEqual(4.5);
      expect(contrast(p.success, p.surface), `${id} success`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("light_scheme_matches_todays_stylesheet", () => {
    const css = fs.readFileSync(path.join(process.cwd(), "src/styles/global.css"), "utf8");
    const root = css.slice(css.indexOf(":root"), css.indexOf("}", css.indexOf(":root")));
    const get = (n) => new RegExp(`--${n}:\\s*([^;]+);`).exec(root)[1].trim();
    const l = SCHEMES.light;
    expect([l.bg, l.surface, l.text, l.textMuted, l.accent, l.accentHover, l.border, l.danger, l.success, l.shadow])
      .toEqual(["bg", "surface", "text", "text-muted", "accent", "accent-hover", "border", "danger", "success", "shadow"].map(get));
    expect(DEFAULT_PALETTE).toEqual({ bg: l.bg, surface: l.surface, text: l.text, accent: l.accent });
  });

  it("derive_palette_has_every_key_and_valid_hex", () => {
    const p = derivePalette({ bg: "#123456", surface: "#234567", text: "#eeeeee", accent: "#ff8800" });
    for (const k of Object.keys(VAR_MAP)) expect(p[k]).toBeTruthy();
    for (const k of ["bg", "surface", "text", "textMuted", "accent", "accentHover", "border", "danger", "success", "onAccent"])
      expect(p[k]).toMatch(/^#[0-9a-f]{6}$/);
  });

  it("derived_muted_and_on_accent_are_legible", () => {
    const r = mulberry32(11);
    let n = 0;
    let guard = 0;
    while (n < 300 && guard++ < 200000) {
      const q = { bg: hexOf(r), surface: hexOf(r), text: hexOf(r), accent: hexOf(r) };
      if (contrast(q.text, q.bg) < 4.5 || contrast(q.text, q.surface) < 4.5) continue;
      n++;
      const p = derivePalette(q);
      expect(contrast(p.textMuted, q.bg)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(p.textMuted, q.surface)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(p.onAccent, q.accent)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(p.onAccent, p.accentHover)).toBeGreaterThanOrEqual(4.5);
    }
    expect(n).toBe(300);
    for (const c of ["#000000", "#ffffff", "#808080"]) {
      const p = derivePalette({ bg: c, surface: c, text: c, accent: c });
      expect(contrast(p.onAccent, c)).toBeGreaterThanOrEqual(4.5);
    }
  });

  const base = { bg: "#ffffff", surface: "#ffffff", text: "#000000", accent: "#000000" };

  it("check_palette_levels", () => {
    expect(checkPalette({ ...base, text: "#ffffff" }).level).toBe("refuse");
    expect(checkPalette({ ...base, text: "#888888" }).level).toBe("warn");
    expect(checkPalette(base).level).toBe("ok");
    expect(checkPalette({ ...base, accent: "#ffffff" }).level).toBe("warn");
    expect(checkPalette({ ...base, surface: "#000000" }).level).toBe("refuse");
    expect(checkPalette(base).message).toMatch(/looks good/i);
  });

  it("check_palette_boundaries", () => {
    const c = (g) => contrast(g, "#ffffff");
    const justOver3 = [...greys].reverse().find((g) => c(g) >= 3);
    const justUnder3 = greys.find((g) => c(g) < 3);
    const justOver45 = [...greys].reverse().find((g) => c(g) >= 4.5);
    const justUnder45 = greys.find((g) => c(g) < 4.5 && c(g) >= 3);
    expect(checkPalette({ ...base, text: justUnder3 }).level).toBe("refuse");
    expect(checkPalette({ ...base, text: justOver3 }).level).toBe("warn");
    expect(checkPalette({ ...base, text: justUnder45 }).level).toBe("warn");
    expect(checkPalette({ ...base, text: justOver45 }).level).toBe("ok");
  });

  it("hover_keeps_on_accent_text_legible", () => {
    for (const accent of ["#008000", "#707070", "#808080", "#4a7a30"]) {
      const p = derivePalette({ ...base, accent });
      expect(contrast(p.onAccent, p.accentHover), accent).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("check_palette_names_the_failing_pair", () => {
    const r = checkPalette({ bg: "#ffffff", surface: "#000000", text: "#ffffff", accent: "#000000" });
    expect(r.level).toBe("refuse");
    expect(r.worst.pair).toBe("background");
    expect(r.worst.ratio).toBeCloseTo(1, 0);
    const r2 = checkPalette({ bg: "#000000", surface: "#ffffff", text: "#ffffff", accent: "#000000" });
    expect(r2.worst.pair).toBe("cards");
    const accentOnly = checkPalette({ ...base, accent: "#ffffff" });
    expect(accentOnly.level).toBe("warn");
    expect(accentOnly.message).toMatch(/accent/i);
  });

  it("scheme_palette_dispatch", () => {
    expect(SCHEME_IDS).toEqual(["auto", "light", "dark", "contrast", "custom"]);
    expect(schemePalette("auto", DEFAULT_PALETTE)).toBeNull();
    expect(schemePalette("dark", DEFAULT_PALETTE)).toBe(SCHEMES.dark);
    expect(schemePalette("contrast", DEFAULT_PALETTE)).toBe(SCHEMES.contrast);
    expect(schemePalette("light", DEFAULT_PALETTE)).toBe(SCHEMES.light);
    expect(schemePalette("custom", DEFAULT_PALETTE)).toEqual(derivePalette(DEFAULT_PALETTE));
  });
});
