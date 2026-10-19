// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, cleanup, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import NotesPage from "./NotesPage";
import { SettingsProvider } from "../SettingsContext";

const logged = [];
const api = {
  listHighlights: vi.fn(),
  listBooks: vi.fn(),
  updateHighlight: vi.fn(),
  deleteHighlight: vi.fn(),
};
vi.mock("../api", () => ({
  api: {
    listHighlights: (...a) => api.listHighlights(...a),
    listBooks: (...a) => api.listBooks(...a),
    updateHighlight: (...a) => api.updateHighlight(...a),
    deleteHighlight: (...a) => api.deleteHighlight(...a),
  },
  logEvent: (type, fields) => logged.push({ type, ...fields }),
}));

const hl = (over) => ({
  id: 1,
  book_id: 2,
  micro_session_id: 100,
  chapter_index: 1,
  chapter_title: "Down the Rabbit-Hole",
  session_index: 0,
  session_number: 3,
  start: 0,
  end: 10,
  quote: "Alice was beginning",
  color: "yellow",
  comment: null,
  created_at: "2026-10-18T10:00:00",
  updated_at: "2026-10-18T10:00:00",
  ...over,
});

const BOOK = {
  id: 2,
  title: "Alice's Adventures",
  author: "Carroll, Lewis",
  published_year: 1865,
  gutenberg_id: 11,
  is_user_uploaded: false,
};

const DATA = [
  hl({ id: 1 }),
  hl({ id: 2, micro_session_id: 101, session_number: 4, start: 40, quote: "the White Rabbit", color: "blue", comment: "key moment" }),
  hl({ id: 3, micro_session_id: 200, chapter_index: 2, chapter_title: "The Pool of Tears", session_number: 9, quote: "curiouser and curiouser", color: "pink" }),
];

function setup(rows = DATA) {
  api.listHighlights.mockResolvedValue(rows);
  api.listBooks.mockResolvedValue([BOOK]);
  return render(
    <MemoryRouter initialEntries={["/books/2/notes"]}>
      <SettingsProvider>
        <Routes>
          <Route path="/books/:bookId/notes" element={<NotesPage />} />
        </Routes>
      </SettingsProvider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  logged.length = 0;
  Object.values(api).forEach((f) => f.mockReset());
});
afterEach(cleanup);

describe("NotesPage", () => {
  it("each_note_has_a_cite_button_that_opens_the_copy_options", async () => {
    setup();
    const cards = (await screen.findAllByTestId("note-quote")).map((q) => q.closest("article"));
    expect(screen.queryByRole("button", { name: "Copy quote with citation" })).toBeNull();
    fireEvent.click(within(cards[1]).getByRole("button", { name: "Cite" }));
    expect(within(cards[1]).getByRole("button", { name: "Copy quote with citation" })).toBeTruthy();
    expect(within(cards[0]).queryByRole("button", { name: "Copy quote with citation" })).toBeNull();
    fireEvent.click(within(cards[1]).getByRole("button", { name: "Cite" }));
    expect(within(cards[1]).queryByRole("button", { name: "Copy quote with citation" })).toBeNull();
  });

  it("groups_by_chapter_in_reading_order", async () => {
    setup([DATA[2], DATA[1], DATA[0]]);
    const headings = await screen.findAllByRole("heading", { level: 2 });
    expect(headings.map((h) => h.textContent)).toEqual(["Down the Rabbit-Hole", "The Pool of Tears"]);
    const quotes = screen.getAllByTestId("note-quote").map((q) => q.textContent);
    expect(quotes).toEqual(["Alice was beginning", "the White Rabbit", "curiouser and curiouser"]);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toMatch(/Alice's Adventures/);
    expect(screen.getByText("3 highlights")).toBeTruthy();
  });

  it("shows_colour_name_session_number_and_comment", async () => {
    setup();
    await screen.findByText("key moment");
    expect(screen.getByText("Session 4")).toBeTruthy();
    const card = screen.getByText("the White Rabbit").closest("article");
    expect(within(card).getByText("Blue")).toBeTruthy();
  });

  it("colour_filter_shows_only_that_colour_and_the_count_updates", async () => {
    setup();
    await screen.findByText("curiouser and curiouser");
    fireEvent.click(screen.getByRole("radio", { name: "Pink" }));
    expect(screen.queryByText("Alice was beginning")).toBeNull();
    expect(screen.getByText("curiouser and curiouser")).toBeTruthy();
    expect(screen.getByText("Showing 1 of 3")).toBeTruthy();
    fireEvent.click(screen.getByRole("radio", { name: "Green" }));
    expect(screen.getByText(/no green highlights/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("radio", { name: "All" }));
    expect(screen.getAllByTestId("note-quote")).toHaveLength(3);
  });

  it("empty_state_explains_how_to_highlight", async () => {
    setup([]);
    expect(await screen.findByText(/select any text while reading/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /export/i })).toBeNull();
  });

  it("go_to_passage_link_has_ms_and_highlight_ids_and_logs", async () => {
    setup();
    await screen.findByText("key moment");
    const card = screen.getByText("the White Rabbit").closest("article");
    const link = within(card).getByRole("link", { name: "Go to passage" });
    expect(link.getAttribute("href")).toBe("/read/2?ms=101&h=2");
    fireEvent.click(link);
    expect(logged.some((e) => e.type === "highlight_jump" && e.bookId === 2)).toBe(true);
  });

  it("edit_saves_colour_and_comment", async () => {
    api.updateHighlight.mockImplementation((id, patch) => Promise.resolve({ ...DATA[1], ...patch }));
    setup();
    await screen.findByText("key moment");
    const card = screen.getByText("the White Rabbit").closest("article");
    fireEvent.click(within(card).getByRole("button", { name: "Edit" }));
    fireEvent.click(within(card).getByRole("radio", { name: "Green" }));
    fireEvent.change(within(card).getByLabelText("Comment"), { target: { value: "rewritten" } });
    fireEvent.click(within(card).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(api.updateHighlight).toHaveBeenCalledWith(2, { color: "green", comment: "rewritten" })
    );
    await screen.findByText("rewritten");
    expect(within(screen.getByText("the White Rabbit").closest("article")).getByText("Green")).toBeTruthy();
    expect(JSON.stringify(logged)).not.toContain("rewritten");
  });

  it("clearing_the_comment_sends_null", async () => {
    api.updateHighlight.mockImplementation((id, patch) => Promise.resolve({ ...DATA[1], ...patch }));
    setup();
    await screen.findByText("key moment");
    const card = screen.getByText("the White Rabbit").closest("article");
    fireEvent.click(within(card).getByRole("button", { name: "Edit" }));
    fireEvent.change(within(card).getByLabelText("Comment"), { target: { value: "  " } });
    fireEvent.click(within(card).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(api.updateHighlight).toHaveBeenCalledWith(2, { color: "blue", comment: null }));
  });

  it("delete_needs_a_second_press_and_removes_the_card", async () => {
    api.deleteHighlight.mockResolvedValue(null);
    setup();
    await screen.findByText("key moment");
    const card = screen.getByText("the White Rabbit").closest("article");
    fireEvent.click(within(card).getByRole("button", { name: "Delete" }));
    expect(api.deleteHighlight).not.toHaveBeenCalled();
    fireEvent.click(within(card).getByRole("button", { name: "Confirm delete" }));
    await waitFor(() => expect(api.deleteHighlight).toHaveBeenCalledWith(2));
    await waitFor(() => expect(screen.queryByText("the White Rabbit")).toBeNull());
    expect(screen.getByText("2 highlights")).toBeTruthy();
    expect(logged.some((e) => e.type === "highlight_deleted")).toBe(true);
  });

  it("export_downloads_markdown_with_the_expected_name", async () => {
    setup();
    await screen.findByText("key moment");
    let blob = null;
    URL.createObjectURL = vi.fn((b) => {
      blob = b;
      return "blob:x";
    });
    URL.revokeObjectURL = vi.fn();
    let downloadName = null;
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function () {
      downloadName = this.download;
    });
    fireEvent.click(screen.getByRole("button", { name: "Export as Markdown" }));
    expect(downloadName).toBe("Alice's Adventures - notes.md");
    expect(blob).toBeTruthy();
    const text = await new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.readAsText(blob);
    });
    expect(text).toContain("# Alice's Adventures");
    expect(text).toContain("> the White Rabbit");
    expect(text).toContain("key moment");
    expect(logged.find((e) => e.type === "notes_exported")).toMatchObject({ bookId: 2, count: 3 });
    click.mockRestore();
  });

  function captureDownload() {
    let blob = null;
    let name = null;
    URL.createObjectURL = vi.fn((b) => {
      blob = b;
      return "blob:x";
    });
    URL.revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function () {
      name = this.download;
    });
    return { get: () => ({ blob, name }), done: () => click.mockRestore() };
  }
  const readText = (blob) =>
    new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.readAsText(blob);
    });

  it("markdown_export_now_carries_citations_and_a_reference_and_logs_format_and_style", async () => {
    setup();
    await screen.findByText("key moment");
    const dl = captureDownload();
    fireEvent.click(screen.getByRole("button", { name: "Export as Markdown" }));
    const text = await readText(dl.get().blob);
    expect(text).toContain("(Carroll, 1865,");
    expect(text).toContain("## Reference");
    expect(logged.find((e) => e.type === "notes_exported")).toMatchObject({ format: "markdown", style: "apa" });
    dl.done();
  });

  it("csv_export_downloads_a_bom_prefixed_file_with_the_chosen_style", async () => {
    setup();
    await screen.findByText("key moment");
    fireEvent.change(screen.getByLabelText("Export citation style"), { target: { value: "mla" } });
    const dl = captureDownload();
    fireEvent.click(screen.getByRole("button", { name: "Export as CSV" }));
    const { blob, name } = dl.get();
    expect(name).toBe("Alice's Adventures - notes.csv");
    const bytes = new Uint8Array(
      await new Promise((resolve) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.readAsArrayBuffer(blob);
      })
    );
    expect([...bytes.slice(0, 3)]).toEqual([0xef, 0xbb, 0xbf]);
    const text = await readText(blob);
    expect(text).toContain("book,author,chapter,chapter_title,quote");
    expect(text).toContain("(Carroll, “Down the Rabbit-Hole”)");
    expect(text).not.toContain("1865,");
    expect(logged.find((e) => e.type === "notes_exported")).toMatchObject({ format: "csv", style: "mla", count: 3 });
    dl.done();
  });

  it("notes_opened_logged_once_with_count", async () => {
    setup();
    await screen.findByText("key moment");
    fireEvent.click(screen.getByRole("radio", { name: "Pink" }));
    expect(logged.filter((e) => e.type === "notes_opened")).toEqual([
      { type: "notes_opened", bookId: 2, count: 3 },
    ]);
  });

  it("exports_still_work_when_the_book_is_missing_from_the_library_list", async () => {
    api.listBooks.mockResolvedValue([]);
    setup();
    await screen.findByText("key moment");
    const dl = captureDownload();
    fireEvent.click(screen.getByRole("button", { name: "Export as CSV" }));
    const csvText = await readText(dl.get().blob);
    expect(csvText).toContain("book,author,chapter,chapter_title,quote");
    expect(csvText).toContain("key moment");
    dl.done();

    const dl2 = captureDownload();
    fireEvent.click(screen.getByRole("button", { name: "Export as Markdown" }));
    expect(await readText(dl2.get().blob)).toContain("key moment");
    dl2.done();
  });

  it("load_failure_shows_a_message", async () => {
    api.listBooks.mockResolvedValue([]);
    api.listHighlights.mockImplementation(() => {
      throw new Error("down");
    });
    render(
      <MemoryRouter initialEntries={["/books/2/notes"]}>
        <SettingsProvider>
          <Routes>
            <Route path="/books/:bookId/notes" element={<NotesPage />} />
          </Routes>
        </SettingsProvider>
      </MemoryRouter>
    );
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toMatch(/could not load/i);
  });

  it("links_back_to_reading_and_the_library", async () => {
    setup();
    await screen.findByText("key moment");
    expect(screen.getByRole("link", { name: "Back to reading" }).getAttribute("href")).toBe("/read/2");
    expect(screen.getByRole("link", { name: "Library" }).getAttribute("href")).toBe("/library");
  });

  it("a_double_click_on_confirm_delete_sends_one_request", async () => {
    let release;
    api.deleteHighlight.mockImplementation(() => new Promise((r) => (release = r)));
    setup();
    await screen.findByText("key moment");
    const card = screen.getByText("the White Rabbit").closest("article");
    fireEvent.click(within(card).getByRole("button", { name: "Delete" }));
    const confirm = within(card).getByRole("button", { name: "Confirm delete" });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    expect(api.deleteHighlight).toHaveBeenCalledTimes(1);
    release(null);
    await waitFor(() => expect(screen.queryByText("the White Rabbit")).toBeNull());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("a_double_click_on_save_sends_one_request", async () => {
    let release;
    api.updateHighlight.mockImplementation(() => new Promise((r) => (release = r)));
    setup();
    await screen.findByText("key moment");
    const card = screen.getByText("the White Rabbit").closest("article");
    fireEvent.click(within(card).getByRole("button", { name: "Edit" }));
    const save = within(card).getByRole("button", { name: "Save" });
    fireEvent.click(save);
    fireEvent.click(save);
    expect(api.updateHighlight).toHaveBeenCalledTimes(1);
    release({ ...DATA[1], comment: "x" });
    await screen.findByText("x");
  });

  it("the_download_url_is_released_after_the_click_not_during_it", async () => {
    vi.useFakeTimers();
    try {
      setup();
      await vi.waitFor(() => expect(screen.getByText("key moment")).toBeTruthy());
      URL.createObjectURL = vi.fn(() => "blob:x");
      URL.revokeObjectURL = vi.fn();
      const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
      fireEvent.click(screen.getByRole("button", { name: "Export as Markdown" }));
      expect(URL.revokeObjectURL).not.toHaveBeenCalled();
      vi.advanceTimersByTime(1500);
      expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:x");
      click.mockRestore();
    } finally {
      vi.useRealTimers();
    }
  });
});
