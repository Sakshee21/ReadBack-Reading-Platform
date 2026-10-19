// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { SettingsProvider, useSettings } from "./SettingsContext";

function Probe() {
  const { citationStyle, setCitationStyle } = useSettings();
  return (
    <div>
      <span data-testid="style">{citationStyle}</span>
      <button onClick={() => setCitationStyle("mla")}>mla</button>
      <button onClick={() => setCitationStyle("harvard")}>bad</button>
    </div>
  );
}

beforeEach(() => localStorage.clear());
afterEach(cleanup);

describe("citation style setting", () => {
  it("defaults_to_apa", () => {
    render(
      <SettingsProvider>
        <Probe />
      </SettingsProvider>
    );
    expect(screen.getByTestId("style").textContent).toBe("apa");
  });

  it("is_remembered", () => {
    render(
      <SettingsProvider>
        <Probe />
      </SettingsProvider>
    );
    fireEvent.click(screen.getByText("mla"));
    cleanup();
    render(
      <SettingsProvider>
        <Probe />
      </SettingsProvider>
    );
    expect(screen.getByTestId("style").textContent).toBe("mla");
  });

  it("refuses_a_style_it_does_not_know_and_repairs_a_bad_stored_value", () => {
    localStorage.setItem("readback_settings", JSON.stringify({ citationStyle: "vancouver" }));
    render(
      <SettingsProvider>
        <Probe />
      </SettingsProvider>
    );
    expect(screen.getByTestId("style").textContent).toBe("apa");
    fireEvent.click(screen.getByText("bad"));
    expect(screen.getByTestId("style").textContent).toBe("apa");
  });
});
