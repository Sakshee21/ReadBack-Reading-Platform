// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { SettingsProvider } from "../SettingsContext";
import SettingsPanel from "./SettingsPanel";

vi.mock("../api", () => ({ logEvent: () => {} }));
vi.mock("./AmbientSound", () => ({ default: () => null }));

beforeEach(() => localStorage.clear());
afterEach(cleanup);

function setup() {
  return render(
    <SettingsProvider>
      <SettingsPanel open onClose={() => {}} />
    </SettingsProvider>
  );
}

describe("Settings panel theme tags", () => {
  it("has_a_show_theme_tags_switch_that_is_off_by_default", () => {
    setup();
    const box = screen.getByRole("checkbox", { name: "Show theme tags" });
    expect(box.checked).toBe(false);
  });

  it("turning_it_on_is_remembered", () => {
    setup();
    fireEvent.click(screen.getByRole("checkbox", { name: "Show theme tags" }));
    expect(JSON.parse(localStorage.getItem("readback_settings")).showThemeTags).toBe(true);
    cleanup();
    setup();
    expect(screen.getByRole("checkbox", { name: "Show theme tags" }).checked).toBe(true);
  });
});
