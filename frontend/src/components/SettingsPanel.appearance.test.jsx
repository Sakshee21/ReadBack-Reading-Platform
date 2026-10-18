// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, act, cleanup } from "@testing-library/react";
import { SettingsProvider } from "../SettingsContext";
import SettingsPanel from "./SettingsPanel";
import { SCHEMES } from "../theme/schemes";

const logged = [];
vi.mock("../api", () => ({ logEvent: (type, fields) => logged.push({ type, ...fields }) }));
vi.mock("./AmbientSound", () => ({ default: () => null }));

const root = document.documentElement;

function setup() {
  return render(
    <SettingsProvider>
      <SettingsPanel open onClose={() => {}} />
    </SettingsProvider>
  );
}
const pick = (name) => fireEvent.click(screen.getByRole("radio", { name }));
const setColor = (name, value) => fireEvent.change(screen.getByLabelText(name), { target: { value } });
const themeEvents = () => logged.filter((e) => e.type === "theme_changed");

beforeEach(() => {
  logged.length = 0;
  localStorage.clear();
  root.removeAttribute("style");
  root.removeAttribute("data-scheme");
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("Settings panel appearance", () => {
  it("lists_the_five_options_with_auto_selected", () => {
    setup();
    for (const n of ["Automatic", "Light", "Dark", "Black and white", "Custom"])
      expect(screen.getByRole("radio", { name: n })).toBeTruthy();
    expect(screen.getByRole("radio", { name: "Automatic" }).checked).toBe(true);
  });

  it("choosing_dark_applies_it_and_logs", () => {
    setup();
    pick("Dark");
    expect(root.style.getPropertyValue("--bg")).toBe(SCHEMES.dark.bg);
    expect(themeEvents()).toEqual([{ type: "theme_changed", scheme: "dark" }]);
  });

  it("choosing_auto_clears_the_theme", () => {
    setup();
    pick("Dark");
    pick("Automatic");
    expect(root.style.getPropertyValue("--bg")).toBe("");
  });

  it("custom_reveals_four_pickers_with_names", () => {
    setup();
    expect(screen.queryByLabelText("Background")).toBeNull();
    pick("Custom");
    for (const n of ["Background", "Cards", "Text", "Accent"]) expect(screen.getByLabelText(n).type).toBe("color");
  });

  it("good_custom_colour_applies_and_says_looks_good", () => {
    setup();
    pick("Custom");
    setColor("Text", "#000000");
    expect(root.style.getPropertyValue("--text")).toBe("#000000");
    expect(screen.getByRole("status").textContent).toMatch(/looks good/i);
  });

  it("low_contrast_custom_colour_applies_with_a_warning", () => {
    setup();
    pick("Custom");
    setColor("Text", "#8a8a8a");
    expect(root.style.getPropertyValue("--text")).toBe("#8a8a8a");
    expect(screen.getByRole("status").textContent).toMatch(/low contrast/i);
  });

  it("unreadable_custom_colour_is_refused", () => {
    setup();
    pick("Custom");
    setColor("Text", "#000000");
    setColor("Text", "#f7f3ea"); // same as the background
    expect(root.style.getPropertyValue("--text")).toBe("#000000");
    expect(screen.getByRole("status").textContent).toMatch(/not applied/i);
    expect(screen.getByLabelText("Text").value).toBe("#f7f3ea");
  });

  it("palette_edits_log_once_after_the_debounce", () => {
    vi.useFakeTimers();
    setup();
    pick("Custom");
    logged.length = 0;
    for (const c of ["#111111", "#222222", "#333333", "#101010", "#000000"]) setColor("Text", c);
    expect(themeEvents()).toHaveLength(0);
    act(() => vi.advanceTimersByTime(800));
    const ev = themeEvents();
    expect(ev).toHaveLength(1);
    expect(ev[0]).toMatchObject({ scheme: "custom", text: "#000000", level: "ok" });
    expect(typeof ev[0].text_on_bg).toBe("number");
  });

  it("scheme_change_flushes_the_pending_palette_log_first", () => {
    vi.useFakeTimers();
    setup();
    pick("Custom");
    logged.length = 0;
    setColor("Text", "#000000");
    pick("Dark");
    act(() => vi.advanceTimersByTime(2000));
    expect(themeEvents().map((e) => e.scheme)).toEqual(["custom", "dark"]);
  });

  it("unmount_flushes_the_pending_palette_log", () => {
    vi.useFakeTimers();
    const { unmount } = setup();
    pick("Custom");
    logged.length = 0;
    setColor("Text", "#000000");
    unmount();
    expect(themeEvents()).toHaveLength(1);
    act(() => vi.advanceTimersByTime(2000));
    expect(themeEvents()).toHaveLength(1);
  });

  it("refused_colour_is_never_stored", () => {
    setup();
    pick("Custom");
    setColor("Text", "#f7f3ea");
    expect(JSON.parse(localStorage.getItem("readback_settings")).customPalette.text).not.toBe("#f7f3ea");
  });

  it("readout_names_the_failing_pair", () => {
    setup();
    pick("Custom");
    setColor("Background", "#000000");
    setColor("Cards", "#ffffff");
    setColor("Text", "#ffffff");
    expect(screen.getByText(/text on cards 1.0 to 1/i)).toBeTruthy();
  });

  it("reset_returns_to_automatic", () => {
    setup();
    pick("Custom");
    setColor("Text", "#000000");
    logged.length = 0;
    fireEvent.click(screen.getByRole("button", { name: "Reset appearance" }));
    expect(screen.getByRole("radio", { name: "Automatic" }).checked).toBe(true);
    expect(root.style.getPropertyValue("--text")).toBe("");
    expect(themeEvents()).toEqual([{ type: "theme_changed", scheme: "auto", reset: true }]);
  });

  it("plain_theme_toggle_is_disabled_outside_automatic", () => {
    setup();
    const plain = screen.getByRole("checkbox", { name: "Plain theme" });
    expect(plain.disabled).toBe(false);
    pick("Dark");
    expect(plain.disabled).toBe(true);
  });

  it("hint_text_is_present", () => {
    setup();
    expect(screen.getByText(/turns off each book's colours/i)).toBeTruthy();
  });

  it("reset_is_available_in_automatic_too", () => {
    localStorage.setItem(
      "readback_settings",
      JSON.stringify({ scheme: "auto", customPalette: { bg: "#000000", surface: "#000000", text: "#ffffff", accent: "#ff0000" } })
    );
    setup();
    fireEvent.click(screen.getByRole("button", { name: "Reset appearance" }));
    expect(JSON.parse(localStorage.getItem("readback_settings")).customPalette.bg).toBe("#f7f3ea");
  });

  it("the_pickers_show_the_applied_palette_after_a_refused_edit_and_a_scheme_switch", () => {
    setup();
    pick("Custom");
    setColor("Text", "#000000");
    setColor("Text", "#f7f3ea"); // refused
    expect(screen.getByLabelText("Text").value).toBe("#f7f3ea");
    pick("Light");
    pick("Custom");
    expect(screen.getByLabelText("Text").value).toBe("#000000");
  });

  it("the_live_region_announces_only_the_message_not_the_changing_ratio", () => {
    setup();
    pick("Custom");
    const status = screen.getByRole("status");
    expect(status.textContent).not.toMatch(/to 1/);
    expect(screen.getByText(/Text on background [0-9]+.[0-9] to 1/)).toBeTruthy();
  });

  it("plain_theme_explains_why_it_can_be_disabled", () => {
    setup();
    expect(screen.getByText(/only used with automatic/i)).toBeTruthy();
    expect(screen.getByRole("checkbox", { name: "Plain theme" }).getAttribute("aria-describedby")).toBeTruthy();
  });

  it("a_refused_colour_never_reaches_storage", () => {
    setup();
    pick("Custom");
    setColor("Text", "#f7f3ea");
    expect(JSON.parse(localStorage.getItem("readback_settings")).customPalette.text).not.toBe("#f7f3ea");
  });
});
