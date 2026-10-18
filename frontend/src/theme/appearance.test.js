// @vitest-environment jsdom
import { describe, it, expect, beforeEach } from "vitest";
import { normalizeAppearance, applyTheme, applyStoredTheme } from "./appearance";
import { SCHEMES, VAR_MAP, DEFAULT_PALETTE } from "./schemes";

const custom = { bg: "#102030", surface: "#203040", text: "#f0f0f0", accent: "#ffaa00" };

beforeEach(() => {
  document.documentElement.removeAttribute("style");
  document.documentElement.removeAttribute("data-scheme");
  document.documentElement.removeAttribute("data-theme");
});

describe("normalizeAppearance", () => {
  it("defaults_for_garbage", () => {
    const bad = [
      null, "x", [], { scheme: "neon" }, { customPalette: "no" },
      { customPalette: { bg: "red", surface: "#12", text: 5, accent: null } },
    ];
    for (const b of bad) {
      expect(normalizeAppearance(b)).toEqual({ scheme: "auto", customPalette: DEFAULT_PALETTE });
    }
  });
  it("accepts_good_values_and_short_hex", () => {
    const r = normalizeAppearance({ scheme: "dark", customPalette: { ...custom, bg: "#123" } });
    expect(r.scheme).toBe("dark");
    expect(r.customPalette.bg).toBe("#112233");
    expect(r.customPalette.accent).toBe("#ffaa00");
  });
});

describe("stored lock-out palettes", () => {
  it("a_stored_palette_with_unreadable_text_is_replaced_by_the_default", () => {
    const r = normalizeAppearance({
      scheme: "custom",
      customPalette: { bg: "#336699", surface: "#336699", text: "#336699", accent: "#ffaa00" },
    });
    expect(r.customPalette).toEqual(DEFAULT_PALETTE);
    expect(r.scheme).toBe("custom");
  });
  it("a_stored_low_contrast_but_usable_palette_is_kept", () => {
    const keep = { bg: "#ffffff", surface: "#ffffff", text: "#8a8a8a", accent: "#000000" };
    expect(normalizeAppearance({ scheme: "custom", customPalette: keep }).customPalette).toEqual(keep);
  });
});

describe("applyTheme", () => {
  it("apply_dark_sets_every_variable", () => {
    const root = document.documentElement;
    applyTheme("dark", DEFAULT_PALETTE);
    for (const [k, v] of Object.entries(VAR_MAP)) expect(root.style.getPropertyValue(v)).toBe(SCHEMES.dark[k]);
    expect(root.getAttribute("data-scheme")).toBe("dark");
    expect(root.style.colorScheme).toBe("dark");
  });
  it("apply_auto_removes_everything_after_custom", () => {
    const root = document.documentElement;
    applyTheme("custom", custom);
    expect(root.style.getPropertyValue("--bg")).toBe("#102030");
    applyTheme("auto", custom);
    for (const v of Object.values(VAR_MAP)) expect(root.style.getPropertyValue(v)).toBe("");
    expect(root.style.colorScheme).toBe("");
    expect(root.getAttribute("data-scheme")).toBe("auto");
  });
  it("book_tint_attribute_does_not_stop_a_theme", () => {
    const root = document.documentElement;
    root.setAttribute("data-theme", "meadow");
    applyTheme("dark", DEFAULT_PALETTE);
    expect(root.style.getPropertyValue("--bg")).toBe(SCHEMES.dark.bg);
    expect(root.getAttribute("data-theme")).toBe("meadow");
  });
  it("light_scheme_sets_color_scheme_light", () => {
    applyTheme("light", DEFAULT_PALETTE);
    expect(document.documentElement.style.colorScheme).toBe("light");
  });
});

describe("applyStoredTheme", () => {
  const store = (value) => ({ getItem: () => value });
  it("reads_storage", () => {
    applyStoredTheme(store(JSON.stringify({ scheme: "custom", customPalette: custom })));
    expect(document.documentElement.style.getPropertyValue("--bg")).toBe("#102030");
  });
  it("survives_bad_storage", () => {
    const root = document.documentElement;
    expect(() => applyStoredTheme({ getItem: () => { throw new Error("no"); } })).not.toThrow();
    expect(() => applyStoredTheme(store("{not json"))).not.toThrow();
    expect(() => applyStoredTheme(store(null))).not.toThrow();
    expect(root.style.getPropertyValue("--bg")).toBe("");
  });
});
