// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import ResearchLibrary from "./ResearchLibrary";
import { SettingsProvider } from "../SettingsContext";

const api = {
  listResearch: vi.fn(),
  deleteResearchDocument: vi.fn(),
};

vi.mock("../api", () => ({
  API_URL: "http://test",
  api: new Proxy({}, { get: (_t, name) => (...args) => api[name](...args) }),
  logEvent: () => {},
  researchExportUrl: () => "http://test/research/export/sections.csv",
  uploadResearchDocument: vi.fn(),
}));

const doc = (over = {}) => ({
  id: 7,
  title: "Attention Scaffolding",
  authors: "A. Reader",
  doc_kind: "paper",
  year: 2021,
  venue: "IEEE TLT",
  doi: "10.1109/x",
  page_count: 4,
  word_count: 1900,
  section_count: 9,
  status: "ready",
  tagging_consent: false,
  tagging_enabled: false,
  ...over,
});

const mount = () =>
  render(
    <SettingsProvider>
      <MemoryRouter>
        <ResearchLibrary />
      </MemoryRouter>
    </SettingsProvider>
  );

beforeEach(() => {
  api.listResearch.mockResolvedValue([doc()]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("the research library", () => {
  it("lists the reader's own documents", async () => {
    mount();
    expect(await screen.findByText("Attention Scaffolding")).toBeTruthy();
    // Exact, because the page subtitle also contains the word "Papers".
    expect(screen.getByText("Paper")).toBeTruthy();
    expect(screen.getByText(/2021 · IEEE TLT · 4 pages · 9 sections/)).toBeTruthy();
  });

  it("says plainly that research is kept out of the pilot", async () => {
    mount();
    await screen.findByText("Attention Scaffolding");
    expect(screen.getByText(/kept out of the reading pilot/)).toBeTruthy();
    expect(screen.getByText(/not in the pilot exports/)).toBeTruthy();
  });

  it("has no streak, nudge or progress", async () => {
    mount();
    await screen.findByText("Attention Scaffolding");
    const page = document.body.textContent;
    expect(page).not.toContain("streak");
    expect(page).not.toContain("Streak");
    expect(page).not.toContain("% read");
  });

  it("offers its own export", async () => {
    mount();
    await screen.findByText("Attention Scaffolding");
    const link = screen.getByRole("link", { name: /Export your sections and tags as CSV/ });
    expect(link.getAttribute("href")).toBe("http://test/research/export/sections.csv");
  });

  it("shows a converting document as unready and does not link to it", async () => {
    api.listResearch.mockResolvedValue([doc({ status: "processing" })]);
    mount();
    expect(await screen.findByText("Converting…")).toBeTruthy();
    expect(screen.queryByRole("link", { name: /Attention Scaffolding/ })).toBeNull();
  });

  it("shows why a conversion failed", async () => {
    api.listResearch.mockResolvedValue([
      doc({ status: "failed", failure_reason: "This looks like a scanned PDF." }),
    ]);
    mount();
    expect(await screen.findByText("This looks like a scanned PDF.")).toBeTruthy();
  });

  it("names a missing author rather than leaving a gap", async () => {
    api.listResearch.mockResolvedValue([doc({ authors: "" })]);
    mount();
    expect(await screen.findByText("Author not found")).toBeTruthy();
  });

  it("confirms before deleting, and says what goes with it", async () => {
    api.deleteResearchDocument.mockResolvedValue(null);
    mount();
    await screen.findByText("Attention Scaffolding");

    fireEvent.click(screen.getByRole("button", { name: /Delete Attention Scaffolding/ }));
    expect(screen.getByText(/highlights, notes and tags are deleted for good/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Keep it" }));
    expect(api.deleteResearchDocument).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /Delete Attention Scaffolding/ }));
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(api.deleteResearchDocument).toHaveBeenCalledWith(7));
  });

  it("explains itself when empty", async () => {
    api.listResearch.mockResolvedValue([]);
    mount();
    expect(await screen.findByText("Nothing here yet")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Add your first document/ })).toBeTruthy();
  });
});
