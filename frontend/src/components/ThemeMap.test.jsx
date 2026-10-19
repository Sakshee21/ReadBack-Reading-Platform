// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, cleanup, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import ThemeMap from "./ThemeMap";

const logged = [];
const api = { getThemeMap: vi.fn() };
vi.mock("../api", () => ({
  api: { getThemeMap: (...a) => api.getThemeMap(...a) },
  logEvent: (type, fields) => logged.push({ type, ...fields }),
}));

const chapters = [
  { index: 1, title: "Chapter 1", start: 0, end: 2 },
  { index: 2, title: "The Ball", start: 3, end: 5 },
];
const reached = {
  reveal: false,
  total: 6,
  chapters,
  themes: [
    { theme: "romance", label: "Romance & courtship", count: 2, cells: [{ pos: 0, micro_session_id: 10, score: 5 }, { pos: 4, micro_session_id: 14, score: 3 }] },
    { theme: "mystery_detection", label: "Mystery & detection", count: 1, cells: [{ pos: 1, micro_session_id: 11, score: 4 }] },
  ],
};
const whole = {
  ...reached,
  reveal: true,
  themes: [
    { ...reached.themes[0], count: 3, cells: [...reached.themes[0].cells, { pos: 5, micro_session_id: 15, score: 4 }] },
    reached.themes[1],
  ],
};

const renderMap = () =>
  render(
    <MemoryRouter>
      <ThemeMap bookId={2} />
    </MemoryRouter>
  );

beforeEach(() => {
  logged.length = 0;
  localStorage.clear();
  api.getThemeMap.mockReset();
  api.getThemeMap.mockImplementation((_id, reveal) => Promise.resolve(reveal ? whole : reached));
});
afterEach(cleanup);

describe("ThemeMap", () => {
  it("shows_a_row_per_theme_with_a_text_summary_and_cells_that_are_links", async () => {
    renderMap();
    const romance = await screen.findByRole("group", { name: "Romance & courtship: 2 passages" });
    const cells = within(romance).getAllByRole("link");
    expect(cells.map((c) => c.getAttribute("aria-label"))).toEqual([
      "Romance & courtship, strong (5 of 5), Chapter 1",
      "Romance & courtship, light (3 of 5), The Ball",
    ]);
    expect(cells[1].getAttribute("href")).toBe("/read/2?ms=14");
    expect(screen.getByRole("group", { name: "Mystery & detection: 1 passage" })).toBeTruthy();
  });

  it("names_the_chapters_along_the_top", async () => {
    renderMap();
    await screen.findByRole("group", { name: /Romance/ });
    expect(screen.getByText("Chapter 1")).toBeTruthy();
    expect(screen.getByText("The Ball")).toBeTruthy();
  });

  it("each_cell_shows_its_strength_in_a_class_as_well_as_the_text_name", async () => {
    renderMap();
    const romance = await screen.findByRole("group", { name: /Romance/ });
    const [strong, light] = within(romance).getAllByRole("link");
    expect(strong.className).toContain("map-score-5");
    expect(light.className).toContain("map-score-3");
  });

  it("each_cell_has_a_hover_title_with_the_same_words", async () => {
    renderMap();
    const romance = await screen.findByRole("group", { name: /Romance/ });
    const [strong] = within(romance).getAllByRole("link");
    expect(strong.getAttribute("title")).toBe("Romance & courtship, strong (5 of 5), Chapter 1");
  });

  it("a_row_is_one_tab_stop_and_the_arrow_keys_move_along_it", async () => {
    renderMap();
    const romance = await screen.findByRole("group", { name: /Romance/ });
    const [first, second] = within(romance).getAllByRole("link");
    expect(first.getAttribute("tabindex")).toBe("0");
    expect(second.getAttribute("tabindex")).toBe("-1");
    first.focus();
    fireEvent.keyDown(first, { key: "ArrowRight" });
    expect(document.activeElement).toBe(second);
    fireEvent.keyDown(second, { key: "ArrowLeft" });
    expect(document.activeElement).toBe(first);
    fireEvent.keyDown(first, { key: "ArrowLeft" });
    expect(document.activeElement).toBe(first);
  });

  it("says_so_when_there_is_nothing_to_map", async () => {
    api.getThemeMap.mockResolvedValue({ reveal: false, total: 4, chapters, themes: [] });
    renderMap();
    expect(await screen.findByText("No theme tags to map yet.")).toBeTruthy();
  });

  it("showing_the_whole_book_needs_a_confirmed_spoiler_warning", async () => {
    renderMap();
    await screen.findByRole("group", { name: /Romance/ });
    fireEvent.click(screen.getByRole("button", { name: "Show the whole book" }));
    expect(screen.getByText(/may spoil the story/i)).toBeTruthy();
    expect(api.getThemeMap).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByText(/may spoil the story/i)).toBeNull();
    expect(api.getThemeMap).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Show the whole book" }));
    fireEvent.click(screen.getByRole("button", { name: "Show it anyway" }));
    await screen.findByRole("group", { name: "Romance & courtship: 3 passages" });
    expect(api.getThemeMap).toHaveBeenLastCalledWith(2, true);
    expect(logged.some((e) => e.type === "theme_map_revealed")).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "Hide unread parts" }));
    await screen.findByRole("group", { name: "Romance & courtship: 2 passages" });
    expect(api.getThemeMap).toHaveBeenLastCalledWith(2, false);
  });

  it("the_choice_is_not_remembered", async () => {
    renderMap();
    await screen.findByRole("group", { name: /Romance/ });
    fireEvent.click(screen.getByRole("button", { name: "Show the whole book" }));
    fireEvent.click(screen.getByRole("button", { name: "Show it anyway" }));
    await screen.findByRole("group", { name: "Romance & courtship: 3 passages" });
    expect(JSON.stringify({ ...localStorage })).not.toMatch(/reveal|whole/i);
    expect(JSON.stringify({ ...sessionStorage })).not.toMatch(/reveal|whole/i);
    cleanup();
    renderMap();
    await screen.findByRole("group", { name: "Romance & courtship: 2 passages" });
  });

  it("a_slow_older_answer_never_overwrites_a_newer_one", async () => {
    renderMap();
    await screen.findByRole("group", { name: /Romance/ });
    let answerReveal;
    api.getThemeMap.mockImplementationOnce(() => new Promise((resolve) => (answerReveal = resolve)));
    fireEvent.click(screen.getByRole("button", { name: "Show the whole book" }));
    fireEvent.click(screen.getByRole("button", { name: "Show it anyway" }));
    fireEvent.click(await screen.findByRole("button", { name: "Hide unread parts" }));
    await waitFor(() => expect(api.getThemeMap).toHaveBeenCalledTimes(3));
    await screen.findByRole("group", { name: "Romance & courtship: 2 passages" });
    answerReveal(whole);
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.getByRole("group", { name: "Romance & courtship: 2 passages" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Show the whole book" })).toBeTruthy();
  });

  it("a_failed_reveal_keeps_the_controls_and_the_map_so_the_reader_can_go_back", async () => {
    renderMap();
    await screen.findByRole("group", { name: /Romance/ });
    api.getThemeMap.mockRejectedValueOnce(new Error("down"));
    fireEvent.click(screen.getByRole("button", { name: "Show the whole book" }));
    fireEvent.click(screen.getByRole("button", { name: "Show it anyway" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/could not load the theme map/i);
    expect(screen.getByRole("group", { name: "Romance & courtship: 2 passages" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Hide unread parts" }));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });

  it("a_failed_load_says_so", async () => {
    api.getThemeMap.mockRejectedValue(new Error("down"));
    renderMap();
    expect((await screen.findByRole("alert")).textContent).toMatch(/could not load the theme map/i);
  });

  it("logs_opening_once_and_cell_clicks_without_text", async () => {
    renderMap();
    const romance = await screen.findByRole("group", { name: /Romance/ });
    expect(logged.filter((e) => e.type === "theme_map_opened")).toEqual([{ type: "theme_map_opened", bookId: 2 }]);
    fireEvent.click(within(romance).getAllByRole("link")[0]);
    expect(logged.find((e) => e.type === "theme_map_cell_opened")).toMatchObject({ bookId: 2, theme: "romance" });
  });
});
