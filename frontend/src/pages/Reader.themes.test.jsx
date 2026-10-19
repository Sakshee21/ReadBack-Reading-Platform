// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { SettingsProvider } from "../SettingsContext";
import Reader from "./Reader";

const position = (book = {}, msId = 100) => ({
  book: { id: 2, title: "Alice", theme: "meadow", is_user_uploaded: false, theme_tagging_consent: false, theme_tagging_enabled: false, ...book },
  chapter_id: 1,
  chapter_index: 0,
  chapter_title: "One",
  is_first_in_book: false,
  recap: null,
  checkpoint_due: null,
  progress_pct: 10,
  micro_session: {
    id: msId,
    index: 0,
    text: "Some text here.",
    word_count: 3,
    is_cliffhanger_break: false,
    has_visualization_prompt: false,
    parts: [{ id: msId, text: "Some text here." }],
  },
});

const api = {
  getReaderPosition: vi.fn(),
  getStreak: vi.fn(),
  getPace: vi.fn(),
  listMicroSessions: vi.fn(),
  startSession: vi.fn(),
  listHighlights: vi.fn(),
  prefetchThemes: vi.fn(),
};
let prefetchFails = false;
vi.mock("../api", () => ({
  api: new Proxy(
    {},
    {
      get: (_t, name) => (...a) =>
        name === "prefetchThemes" && prefetchFails ? Promise.reject(new Error("down")) : api[name](...a),
    }
  ),
  logEvent: () => {},
}));

function renderReader() {
  return render(
    <MemoryRouter initialEntries={["/read/2"]}>
      <SettingsProvider>
        <Routes>
          <Route path="/read/:bookId" element={<Reader />} />
        </Routes>
      </SettingsProvider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  prefetchFails = false;
  Object.values(api).forEach((f) => f.mockReset());
  api.getStreak.mockResolvedValue({ current_streak: 1, longest_streak: 1 });
  api.getPace.mockResolvedValue({ wpm_recent: null, wpm_average: null, trend: null });
  api.listMicroSessions.mockResolvedValue([]);
  api.startSession.mockResolvedValue({ id: 1 });
  api.listHighlights.mockResolvedValue([]);
  api.prefetchThemes.mockResolvedValue({ queued: 3 });
  window.scrollTo = vi.fn();
  globalThis.ResizeObserver = class {
    observe() {}
    disconnect() {}
  };
});
afterEach(cleanup);

describe("Reader theme tagging", () => {
  it("prefetches_for_an_upload_with_tagging_on", async () => {
    api.getReaderPosition.mockResolvedValue(position({ is_user_uploaded: true, theme_tagging_enabled: true }));
    renderReader();
    await waitFor(() => expect(api.prefetchThemes).toHaveBeenCalledWith(2, 100));
    expect(api.prefetchThemes).toHaveBeenCalledTimes(1);
  });

  it("does_not_prefetch_for_a_book_that_is_not_switched_on", async () => {
    api.getReaderPosition.mockResolvedValue(position());
    renderReader();
    await screen.findByText(/Some text here/);
    cleanup();
    api.getReaderPosition.mockResolvedValue(position({ is_user_uploaded: true, theme_tagging_consent: false }));
    renderReader();
    await screen.findByText(/Some text here/);
    expect(api.prefetchThemes).not.toHaveBeenCalled();
  });

  it("a_failed_prefetch_never_blocks_reading", async () => {
    prefetchFails = true;
    api.getReaderPosition.mockResolvedValue(position({ theme_tagging_enabled: true }));
    renderReader();
    expect(await screen.findByText(/Some text here/)).toBeTruthy();
  });

  it("has_a_themes_link", async () => {
    api.getReaderPosition.mockResolvedValue(position());
    renderReader();
    const link = await screen.findByRole("link", { name: /Themes/ });
    expect(link.getAttribute("href")).toBe("/books/2/themes");
  });
});

describe("Reader theme tags", () => {
  const tags = { themes: [{ theme: "romance", label: "Romance & courtship", score: 5 }], preparing: false };

  beforeEach(() => {
    localStorage.clear();
    api.getPassageThemes = vi.fn().mockResolvedValue(tags);
  });
  const turnOn = () => localStorage.setItem("readback_settings", JSON.stringify({ showThemeTags: true }));

  it("shows_nothing_and_asks_for_nothing_by_default", async () => {
    api.getReaderPosition.mockResolvedValue(position());
    renderReader();
    await screen.findByText(/Some text here/);
    expect(api.getPassageThemes).not.toHaveBeenCalled();
    expect(screen.queryByText("Romance & courtship")).toBeNull();
  });

  it("when_on_shows_the_passage_tags_as_links_to_the_themes_page", async () => {
    turnOn();
    api.getReaderPosition.mockResolvedValue(position());
    renderReader();
    const chip = await screen.findByRole("link", { name: "Romance & courtship" });
    expect(chip.getAttribute("href")).toBe("/books/2/themes");
    expect(api.getPassageThemes).toHaveBeenCalledWith(2, 100);
  });

  it("says_themes_are_being_prepared_for_a_consented_upload_without_tags_yet", async () => {
    turnOn();
    api.getPassageThemes.mockResolvedValue({ themes: [], preparing: true });
    api.getReaderPosition.mockResolvedValue(position({ is_user_uploaded: true, theme_tagging_consent: true }));
    renderReader();
    expect(await screen.findByText(/Themes are still being prepared/)).toBeTruthy();
  });

  it("shows_nothing_when_there_are_no_tags_and_nothing_is_pending", async () => {
    turnOn();
    api.getPassageThemes.mockResolvedValue({ themes: [], preparing: false });
    api.getReaderPosition.mockResolvedValue(position());
    renderReader();
    await screen.findByText(/Some text here/);
    await waitFor(() => expect(api.getPassageThemes).toHaveBeenCalled());
    expect(screen.queryByLabelText("Themes in this passage")).toBeNull();
  });

  it("a_failed_lookup_never_disturbs_reading", async () => {
    turnOn();
    api.getPassageThemes.mockRejectedValue(new Error("down"));
    api.getReaderPosition.mockResolvedValue(position());
    renderReader();
    expect(await screen.findByText(/Some text here/)).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
