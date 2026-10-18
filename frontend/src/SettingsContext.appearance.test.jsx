// @vitest-environment jsdom
import { describe, it, expect, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { SettingsProvider, useSettings } from "./SettingsContext";
import { SCHEMES, DEFAULT_PALETTE } from "./theme/schemes";

const wrapper = ({ children }) => <SettingsProvider>{children}</SettingsProvider>;
const root = document.documentElement;
const stored = () => JSON.parse(localStorage.getItem("readback_settings"));

beforeEach(() => {
  localStorage.clear();
  root.removeAttribute("style");
  root.removeAttribute("data-scheme");
});

describe("SettingsContext appearance", () => {
  it("defaults_to_auto", () => {
    const { result } = renderHook(() => useSettings(), { wrapper });
    expect(result.current.scheme).toBe("auto");
    expect(result.current.customPalette).toEqual(DEFAULT_PALETTE);
  });

  it("set_scheme_applies_and_persists", () => {
    const { result } = renderHook(() => useSettings(), { wrapper });
    act(() => result.current.setScheme("dark"));
    expect(root.style.getPropertyValue("--bg")).toBe(SCHEMES.dark.bg);
    expect(stored().scheme).toBe("dark");
    act(() => result.current.setScheme("auto"));
    expect(root.style.getPropertyValue("--bg")).toBe("");
  });

  it("invalid_scheme_ignored", () => {
    const { result } = renderHook(() => useSettings(), { wrapper });
    act(() => result.current.setScheme("neon"));
    expect(result.current.scheme).toBe("auto");
  });

  it("set_custom_palette_applies_and_normalises", () => {
    const { result } = renderHook(() => useSettings(), { wrapper });
    act(() => result.current.setScheme("custom"));
    act(() => result.current.setCustomPalette({ bg: "#ABC", surface: "nope", text: "#000000", accent: "#123456" }));
    expect(result.current.customPalette.bg).toBe("#aabbcc");
    expect(result.current.customPalette.surface).toBe(DEFAULT_PALETTE.surface);
    expect(root.style.getPropertyValue("--bg")).toBe("#aabbcc");
    expect(stored().customPalette.accent).toBe("#123456");
  });

  it("reset_returns_to_auto_and_default_palette", () => {
    const { result } = renderHook(() => useSettings(), { wrapper });
    act(() => result.current.setScheme("custom"));
    act(() => result.current.setCustomPalette({ ...DEFAULT_PALETTE, bg: "#000000" }));
    act(() => result.current.resetAppearance());
    expect(result.current.scheme).toBe("auto");
    expect(result.current.customPalette).toEqual(DEFAULT_PALETTE);
    expect(root.style.getPropertyValue("--bg")).toBe("");
  });

  it("old_stored_settings_without_appearance_still_load", () => {
    localStorage.setItem("readback_settings", JSON.stringify({ reduceMotion: true }));
    const { result } = renderHook(() => useSettings(), { wrapper });
    expect(result.current.scheme).toBe("auto");
    expect(result.current.reduceMotion).toBe(true);
  });

  it("garbage_stored_appearance_is_replaced", () => {
    localStorage.setItem("readback_settings", JSON.stringify({ scheme: "neon", customPalette: { bg: 4 } }));
    const { result } = renderHook(() => useSettings(), { wrapper });
    expect(result.current.scheme).toBe("auto");
    expect(result.current.customPalette).toEqual(DEFAULT_PALETTE);
  });

  it("unavailable_storage_does_not_throw", () => {
    const orig = Storage.prototype.getItem;
    const origSet = Storage.prototype.setItem;
    Storage.prototype.getItem = () => { throw new Error("blocked"); };
    Storage.prototype.setItem = () => { throw new Error("blocked"); };
    try {
      const { result } = renderHook(() => useSettings(), { wrapper });
      act(() => result.current.setScheme("dark"));
      expect(result.current.scheme).toBe("dark");
    } finally {
      Storage.prototype.getItem = orig;
      Storage.prototype.setItem = origSet;
    }
  });
});
