// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { SettingsProvider } from "../SettingsContext";
import Reader from "./Reader";

const logged = [];
const position = (over = {}) => ({
  book: { id: 2, title: "Alice", theme: "meadow" },
  chapter_id: 1,
  chapter_index: 0,
  chapter_title: "Down the Rabbit-Hole",
  is_first_in_book: false,
  recap: null,
  checkpoint_due: null,
  progress_pct: 10,
  micro_session: {
    id: 100,
    index: 0,
    text: "Alice was beginning.\n\nTo get very tired.",
    word_count: 8,
    is_cliffhanger_break: false,
    has_visualization_prompt: false,
    parts: [{ id: 100, text: "Alice was beginning.\n\nTo get very tired." }],
  },
  ...over,
});

const api = {
  getReaderPosition: vi.fn(),
  getStreak: vi.fn(),
  getPace: vi.fn(),
  listMicroSessions: vi.fn(),
  startSession: vi.fn(),
  listHighlights: vi.fn(),
  jumpToMicroSession: vi.fn(),
};
// A plain rejecting function: a rejecting vi.fn leaks an unhandled rejection from vitest.
let highlightsDown = false;
vi.mock("../api", () => ({
  api: new Proxy(
    {},
    {
      get: (_t, name) => (...a) =>
        name === "listHighlights" && highlightsDown ? Promise.reject(new Error("down")) : api[name](...a),
    }
  ),
  logEvent: (type, fields) => logged.push({ type, ...fields }),
}));

function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="loc">{loc.pathname + loc.search}</div>;
}

function renderReader(url) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <SettingsProvider>
        <Routes>
          <Route
            path="/read/:bookId"
            element={
              <>
                <Reader />
                <LocationProbe />
              </>
            }
          />
        </Routes>
      </SettingsProvider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  logged.length = 0;
  highlightsDown = false;
  Object.values(api).forEach((f) => f.mockReset());
  api.getStreak.mockResolvedValue({ current_streak: 1, longest_streak: 1 });
  api.getPace.mockResolvedValue({ wpm_recent: null, wpm_average: null, trend: null });
  api.listMicroSessions.mockResolvedValue([]);
  api.startSession.mockResolvedValue({ id: 1 });
  api.listHighlights.mockResolvedValue([
    { id: 3, micro_session_id: 100, start: 0, end: 5, quote: "Alice", color: "green", comment: null },
  ]);
  api.getReaderPosition.mockResolvedValue(position());
  window.scrollTo = vi.fn();
  globalThis.ResizeObserver = class {
    observe() {}
    disconnect() {}
  };
});
afterEach(cleanup);

describe("Reader highlights", () => {
  it("draws_the_readers_highlights_in_the_passage", async () => {
    const { container } = renderReader("/read/2");
    await waitFor(() => expect(container.querySelector("mark[data-highlight-id='3']")).toBeTruthy());
    expect(container.querySelector("mark").textContent).toBe("Alice");
    expect(container.querySelectorAll(".reader-content p").length).toBeGreaterThan(1);
  });

  it("notes_link_points_to_the_notes_page", async () => {
    renderReader("/read/2");
    const link = await screen.findByRole("link", { name: /Notes/ });
    expect(link.getAttribute("href")).toBe("/books/2/notes");
  });

  it("a_failed_highlight_load_still_shows_the_text", async () => {
    highlightsDown = true;
    renderReader("/read/2");
    expect(await screen.findByText(/Alice was beginning/)).toBeTruthy();
  });

  it("ms_link_peeks_at_the_passage_does_not_jump_and_clears_the_url", async () => {
    api.getReaderPosition.mockImplementation((bookId, ms) =>
      Promise.resolve(
        ms
          ? position({
              micro_session: {
                id: 55,
                index: 4,
                text: "Curiouser and curiouser.",
                word_count: 3,
                is_cliffhanger_break: false,
                has_visualization_prompt: false,
                parts: [{ id: 55, text: "Curiouser and curiouser." }],
              },
            })
          : position()
      )
    );
    renderReader("/read/2?ms=55&h=3");
    expect(await screen.findByText(/Curiouser and curiouser/)).toBeTruthy();
    expect(api.getReaderPosition).toHaveBeenCalledWith("2", 55);
    expect(api.jumpToMicroSession).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByTestId("loc").textContent).toBe("/read/2"));
  });
});
