// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, cleanup, within } from "@testing-library/react";
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

/** Six passages in the book, the reader has reached three. */
const reached = {
  reveal: false,
  total: 6,
  reached: 3,
  chapters,
  themes: [
    {
      theme: "romance",
      label: "Romance & courtship",
      count: 2,
      cells: [
        { pos: 0, micro_session_id: 10, score: 5 },
        { pos: 2, micro_session_id: 12, score: 3 },
      ],
    },
    {
      theme: "mystery_detection",
      label: "Mystery & detection",
      count: 1,
      cells: [{ pos: 1, micro_session_id: 11, score: 4 }],
    },
  ],
};

const renderMap = () =>
  render(
    <MemoryRouter>
      <ThemeMap bookId={2} />
    </MemoryRouter>
  );

const columnsOf = (grid) => grid.style.gridTemplateColumns;
const romanceRow = () => screen.findByRole("group", { name: /Romance/ });
const gridIn = (row) => row.querySelector(".map-grid");

beforeEach(() => {
  logged.length = 0;
  localStorage.clear();
  api.getThemeMap.mockReset();
  api.getThemeMap.mockResolvedValue(reached);
});
afterEach(cleanup);

describe("ThemeMap", () => {
  it("shows_a_row_per_theme_with_a_text_summary_and_cells_that_are_links", async () => {
    renderMap();
    const romance = await screen.findByRole("group", { name: "Romance & courtship: 2 passages" });
    const cells = within(romance).getAllByRole("link");
    expect(cells.map((c) => c.getAttribute("aria-label"))).toEqual([
      "Romance & courtship, strong (5 of 5), Chapter 1",
      "Romance & courtship, light (3 of 5), Chapter 1",
    ]);
    expect(cells[1].getAttribute("href")).toBe("/read/2?ms=12");
    expect(screen.getByRole("group", { name: "Mystery & detection: 1 passage" })).toBeTruthy();
  });

  it("each_cell_shows_its_strength_in_a_class_as_well_as_the_text_name", async () => {
    const romance = await (renderMap(), romanceRow());
    const [strong, light] = within(romance).getAllByRole("link");
    expect(strong.className).toContain("map-score-5");
    expect(light.className).toContain("map-score-3");
  });

  it("each_cell_has_a_hover_title_with_the_same_words", async () => {
    const romance = await (renderMap(), romanceRow());
    const [strong] = within(romance).getAllByRole("link");
    expect(strong.getAttribute("title")).toBe("Romance & courtship, strong (5 of 5), Chapter 1");
  });

  it("a_row_is_one_tab_stop_and_the_arrow_keys_move_along_it", async () => {
    const romance = await (renderMap(), romanceRow());
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
    api.getThemeMap.mockResolvedValue({ reveal: false, total: 4, reached: 2, chapters, themes: [] });
    renderMap();
    expect(await screen.findByText("No theme tags to map yet.")).toBeTruthy();
  });

  it("a_failed_load_says_so", async () => {
    api.getThemeMap.mockRejectedValue(new Error("down"));
    renderMap();
    expect((await screen.findByRole("alert")).textContent).toMatch(/could not load the theme map/i);
  });

  it("logs_opening_once_and_cell_clicks_without_text", async () => {
    const romance = await (renderMap(), romanceRow());
    expect(logged.filter((e) => e.type === "theme_map_opened")).toEqual([
      { type: "theme_map_opened", bookId: 2 },
    ]);
    fireEvent.click(within(romance).getAllByRole("link")[0]);
    expect(logged.find((e) => e.type === "theme_map_cell_opened")).toMatchObject({
      bookId: 2,
      theme: "romance",
    });
  });
});

describe("how much of the book the chart spans", () => {
  it("fits what the reader has read by default", async () => {
    const romance = await (renderMap(), romanceRow());
    // Three of six passages reached, so three columns - not six.
    expect(columnsOf(gridIn(romance))).toBe("repeat(3, minmax(7px, 1fr))");
    expect(screen.getByText(/Only passages you have reached are shown/)).toBeTruthy();
  });

  it("spans the whole book when asked, and offers the way back", async () => {
    renderMap();
    await romanceRow();
    fireEvent.click(screen.getByRole("button", { name: "Show the whole book" }));

    expect(columnsOf(gridIn(await romanceRow()))).toBe("repeat(6, minmax(7px, 1fr))");
    const back = screen.getByRole("button", { name: /Show only what I/ });
    expect(back).toBeTruthy();

    fireEvent.click(back);
    expect(columnsOf(gridIn(await romanceRow()))).toBe("repeat(3, minmax(7px, 1fr))");
  });

  it("never asks the server for more than it already has", async () => {
    // The guarantee: widening the chart is a drawing choice, so there is
    // nothing extra in hand to spoil with.
    renderMap();
    await romanceRow();
    fireEvent.click(screen.getByRole("button", { name: "Show the whole book" }));
    await romanceRow();

    expect(api.getThemeMap).toHaveBeenCalledTimes(1);
    expect(api.getThemeMap).toHaveBeenCalledWith(2);
    expect(api.getThemeMap).not.toHaveBeenCalledWith(2, true);
  });

  it("shows no tag beyond the reader's position even across the whole book", async () => {
    renderMap();
    await romanceRow();
    fireEvent.click(screen.getByRole("button", { name: "Show the whole book" }));

    const romance = await romanceRow();
    const columns = within(romance)
      .getAllByRole("link")
      .map((a) => Number(a.style.gridColumn));
    // Three passages reached, so nothing may be drawn past column 3.
    expect(Math.max(...columns)).toBeLessThanOrEqual(3);
    expect(screen.getByText(/only passages you have reached are tagged/i)).toBeTruthy();
  });

  it("offers nothing to widen once the whole book has been read", async () => {
    api.getThemeMap.mockResolvedValue({ ...reached, reached: 6 });
    renderMap();
    await romanceRow();
    expect(screen.getByRole("button", { name: "Show the whole book" }).disabled).toBe(true);
  });

  it("logs the change of scale", async () => {
    renderMap();
    await romanceRow();
    fireEvent.click(screen.getByRole("button", { name: "Show the whole book" }));
    expect(logged.find((e) => e.type === "theme_map_scale_changed")).toMatchObject({
      bookId: 2,
      scale: "whole",
    });
  });

  it("the_choice_is_not_remembered", async () => {
    renderMap();
    await romanceRow();
    fireEvent.click(screen.getByRole("button", { name: "Show the whole book" }));
    await romanceRow();
    expect(JSON.stringify({ ...localStorage })).not.toMatch(/scale|whole/i);
    expect(JSON.stringify({ ...sessionStorage })).not.toMatch(/scale|whole/i);
    cleanup();
    renderMap();
    expect(columnsOf(gridIn(await romanceRow()))).toBe("repeat(3, minmax(7px, 1fr))");
  });
});

describe("chapter labels", () => {
  it("uses short numbers, not crushed titles", async () => {
    renderMap();
    await romanceRow();
    expect(screen.getByText("Ch 1")).toBeTruthy();
    expect(screen.queryByText("The Ball")).toBeNull();
  });

  it("keeps the full title as the hover text", async () => {
    renderMap();
    await romanceRow();
    expect(screen.getByText("Ch 1").getAttribute("title")).toBe("Chapter 1");
  });

  it("keeps the full title in every square's accessible name", async () => {
    const romance = await (renderMap(), romanceRow());
    expect(within(romance).getAllByRole("link")[0].getAttribute("aria-label")).toContain(
      "Chapter 1"
    );
  });

  it("thins the labels on a book with many short chapters", async () => {
    const many = Array.from({ length: 30 }, (_, i) => ({
      index: i + 1,
      title: `Chapter ${i + 1}`,
      start: i * 2,
      end: i * 2 + 1,
    }));
    api.getThemeMap.mockResolvedValue({
      reveal: false,
      total: 60,
      reached: 60,
      chapters: many,
      themes: [
        {
          theme: "romance",
          label: "Romance & courtship",
          count: 1,
          cells: [{ pos: 0, micro_session_id: 10, score: 5 }],
        },
      ],
    });
    renderMap();
    await romanceRow();
    const labels = document.querySelectorAll(".map-chapter");
    expect(labels.length).toBeGreaterThan(0);
    expect(labels.length).toBeLessThan(many.length);
  });

  it("draws a divider per chapter in the drawn range", async () => {
    renderMap();
    await romanceRow();
    // Three passages reached, so chapter 2 (starting at passage 4) is not in
    // range yet and gets no divider.
    expect(document.querySelectorAll(".map-rule").length).toBe(1);

    fireEvent.click(screen.getByRole("button", { name: "Show the whole book" }));
    await romanceRow();
    expect(document.querySelectorAll(".map-rule").length).toBe(chapters.length);
  });
});

describe("by chapter", () => {
  it("gives one square per chapter at its strongest score", async () => {
    renderMap();
    await romanceRow();
    fireEvent.click(screen.getByRole("button", { name: "By chapter" }));

    const romance = await romanceRow();
    const cells = within(romance).getAllByRole("link");
    // Both romance passages are in chapter 1, so one square, scored 5.
    expect(cells).toHaveLength(1);
    expect(cells[0].className).toContain("map-score-5");
    expect(cells[0].getAttribute("aria-label")).toBe(
      "Romance & courtship, strong (5 of 5), Chapter 1, 2 passages"
    );
  });

  it("links a chapter square to its strongest passage", async () => {
    renderMap();
    await romanceRow();
    fireEvent.click(screen.getByRole("button", { name: "By chapter" }));
    const [cell] = within(await romanceRow()).getAllByRole("link");
    expect(cell.getAttribute("href")).toBe("/read/2?ms=10");
  });

  it("is a column per chapter, so a long book stays readable", async () => {
    renderMap();
    await romanceRow();
    fireEvent.click(screen.getByRole("button", { name: "By chapter" }));
    // One chapter is in range (the reader has reached passage 3 of 6).
    expect(columnsOf(gridIn(await romanceRow()))).toBe("repeat(1, minmax(7px, 1fr))");
  });

  it("says what a square means, and which view is on", async () => {
    renderMap();
    await romanceRow();
    expect(screen.getByRole("button", { name: "By passage" }).getAttribute("aria-pressed")).toBe(
      "true"
    );

    fireEvent.click(screen.getByRole("button", { name: "By chapter" }));
    expect(screen.getByText(/Each square is a chapter/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "By chapter" }).getAttribute("aria-pressed")).toBe(
      "true"
    );
    expect(logged.find((e) => e.type === "theme_map_view_changed")).toMatchObject({
      view: "chapter",
    });
  });

  it("shows no chapter the reader has not reached", async () => {
    renderMap();
    await romanceRow();
    fireEvent.click(screen.getByRole("button", { name: "By chapter" }));
    fireEvent.click(screen.getByRole("button", { name: "Show the whole book" }));

    const romance = await romanceRow();
    // Two chapters wide now, but only the reached one carries a square.
    expect(columnsOf(gridIn(romance))).toBe("repeat(2, minmax(7px, 1fr))");
    expect(within(romance).getAllByRole("link")).toHaveLength(1);
  });
});

describe("reading the chart", () => {
  it("keeps the darker-means-stronger wording and adds a key", async () => {
    renderMap();
    await romanceRow();
    expect(screen.getByText(/Darker means stronger/)).toBeTruthy();
    const key = screen.getByRole("list", { name: "Strength key" });
    expect(key.textContent).toContain("light (3 of 5)");
    expect(key.textContent).toContain("clear (4 of 5)");
    expect(key.textContent).toContain("strong (5 of 5)");
  });

  it("the chart can be scrolled sideways from the keyboard", async () => {
    renderMap();
    await romanceRow();
    const scroller = screen.getByRole("group", { name: /scrollable sideways/i });
    expect(scroller.getAttribute("tabindex")).toBe("0");
  });

  it("gives every square a floor width rather than squeezing it", async () => {
    api.getThemeMap.mockResolvedValue({ ...reached, total: 900, reached: 900 });
    renderMap();
    expect(columnsOf(gridIn(await romanceRow()))).toBe("repeat(900, minmax(7px, 1fr))");
  });
});
