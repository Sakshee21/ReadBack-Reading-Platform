// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, act, cleanup, waitFor } from "@testing-library/react";
import HighlightableText from "./HighlightableText";
import { SettingsProvider } from "../SettingsContext";

const logged = [];
const api = {
  createHighlight: vi.fn(),
  updateHighlight: vi.fn(),
  deleteHighlight: vi.fn(),
};
vi.mock("../api", () => ({
  api: {
    createHighlight: (...a) => api.createHighlight(...a),
    updateHighlight: (...a) => api.updateHighlight(...a),
    deleteHighlight: (...a) => api.deleteHighlight(...a),
  },
  logEvent: (type, fields) => logged.push({ type, ...fields }),
}));

const TEXT = "Hello world.\n\nSecond paragraph here.";
const EMOJI = "\u{1F600} Hello there friend.";

const row = (over = {}) => ({
  id: 7,
  book_id: 2,
  micro_session_id: 11,
  start: 0,
  end: 5,
  quote: "Hello",
  color: "yellow",
  comment: null,
  ...over,
});

function setup(props = {}) {
  const onChanged = vi.fn();
  const utils = render(
    <HighlightableText
      text={TEXT}
      bookId={2}
      microSessionId={11}
      enabled
      highlights={[]}
      onChanged={onChanged}
      {...props}
    />
  );
  return { ...utils, onChanged };
}

function select(node, a, b) {
  const range = document.createRange();
  range.setStart(node, a);
  range.setEnd(node, b);
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
  act(() => {
    document.dispatchEvent(new Event("selectionchange"));
  });
}

const firstText = (container) => container.querySelector("p").firstChild;

beforeEach(() => {
  logged.length = 0;
  Object.values(api).forEach((f) => f.mockReset());
});
afterEach(() => {
  cleanup();
  window.getSelection().removeAllRanges();
});

describe("HighlightableText", () => {
  it("selecting_text_shows_the_bar_only_when_enabled", () => {
    const { container } = setup();
    expect(screen.queryByRole("group", { name: "Highlight" })).toBeNull();
    select(firstText(container), 6, 11);
    expect(screen.getByRole("group", { name: "Highlight" })).toBeTruthy();
    for (const c of ["Yellow", "Green", "Blue", "Pink", "Orange", "Purple"])
      expect(screen.getByRole("button", { name: c })).toBeTruthy();
  });

  it("bar_disappears_when_enabled_turns_false", () => {
    const onChanged = vi.fn();
    const props = { text: TEXT, bookId: 2, microSessionId: 11, highlights: [], onChanged };
    const { container, rerender } = render(<HighlightableText {...props} enabled />);
    select(firstText(container), 6, 11);
    expect(screen.getByRole("group", { name: "Highlight" })).toBeTruthy();
    rerender(<HighlightableText {...props} enabled={false} />);
    expect(screen.queryByRole("group", { name: "Highlight" })).toBeNull();
  });

  it("not_enabled_never_shows_the_bar", () => {
    const { container } = setup({ enabled: false });
    select(firstText(container), 6, 11);
    expect(screen.queryByRole("group", { name: "Highlight" })).toBeNull();
  });

  it("choosing_a_colour_creates_with_code_point_positions_and_logs_without_text", async () => {
    api.createHighlight.mockResolvedValue(row({ id: 1, start: 2, end: 7, quote: "Hello", color: "green" }));
    const { container, onChanged } = setup({ text: EMOJI });
    const node = firstText(container);
    select(node, EMOJI.indexOf("Hello"), EMOJI.indexOf("Hello") + 5);
    fireEvent.click(screen.getByRole("button", { name: "Green" }));
    await waitFor(() => expect(api.createHighlight).toHaveBeenCalled());
    expect(api.createHighlight).toHaveBeenCalledWith(2, {
      micro_session_id: 11,
      start: 3 - 1,
      end: 7,
      color: "green",
      comment: null,
    });
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(onChanged.mock.calls[0][0].map((h) => h.id)).toEqual([1]);
    const ev = logged.find((e) => e.type === "highlight_created");
    expect(ev).toMatchObject({ color: "green", length: 5, has_comment: false, bookId: 2, microSessionId: 11 });
    expect(JSON.stringify(logged)).not.toContain("Hello");
    expect(screen.queryByRole("group", { name: "Highlight" })).toBeNull();
  });

  it("comment_is_sent_and_not_logged", async () => {
    api.createHighlight.mockResolvedValue(row({ comment: "secret thought" }));
    const { container } = setup();
    select(firstText(container), 0, 5);
    fireEvent.change(screen.getByLabelText("Comment (optional)"), { target: { value: "secret thought" } });
    fireEvent.click(screen.getByRole("button", { name: "Blue" }));
    await waitFor(() => expect(api.createHighlight).toHaveBeenCalled());
    expect(api.createHighlight.mock.calls[0][1].comment).toBe("secret thought");
    await waitFor(() => expect(logged.some((e) => e.type === "highlight_created")).toBe(true));
    expect(logged.find((e) => e.type === "highlight_created").has_comment).toBe(true);
    expect(JSON.stringify(logged)).not.toContain("secret thought");
  });

  it("overlap_409_shows_the_message_and_keeps_the_bar", async () => {
    api.createHighlight.mockRejectedValue(Object.assign(new Error("That overlaps"), { status: 409 }));
    const { container, onChanged } = setup();
    select(firstText(container), 0, 5);
    fireEvent.click(screen.getByRole("button", { name: "Pink" }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/overlaps an existing highlight/i);
    expect(screen.getByRole("group", { name: "Highlight" })).toBeTruthy();
    expect(onChanged).not.toHaveBeenCalled();
  });

  it("other_failures_show_a_generic_message", async () => {
    api.createHighlight.mockRejectedValue(new Error("boom"));
    const { container } = setup();
    select(firstText(container), 0, 5);
    fireEvent.click(screen.getByRole("button", { name: "Pink" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/could not save that highlight/i);
  });

  it("activating_a_mark_opens_edit_mode_and_saves_changes", async () => {
    api.updateHighlight.mockImplementation((id, patch) => Promise.resolve(row({ id, ...patch })));
    const { container, onChanged } = setup({ highlights: [row({ comment: "old" })] });
    const mark = container.querySelector("mark[data-highlight-id='7']");
    expect(mark.textContent).toBe("Hello");
    fireEvent.click(mark);
    const box = screen.getByLabelText("Comment (optional)");
    expect(box.value).toBe("old");
    fireEvent.change(box, { target: { value: "new" } });
    fireEvent.click(screen.getByRole("button", { name: "Save comment" }));
    await waitFor(() => expect(api.updateHighlight).toHaveBeenCalledWith(7, { comment: "new" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());

    fireEvent.click(mark);
    fireEvent.click(screen.getByRole("button", { name: "Purple" }));
    await waitFor(() => expect(api.updateHighlight).toHaveBeenCalledWith(7, { color: "purple" }));
    await waitFor(() => expect(logged.filter((e) => e.type === "highlight_edited").length).toBeGreaterThan(0));
    expect(JSON.stringify(logged)).not.toContain("new");
  });

  it("enter_on_a_mark_opens_edit_mode", () => {
    const { container } = setup({ highlights: [row()] });
    const mark = container.querySelector("mark");
    fireEvent.keyDown(mark, { key: "Enter" });
    expect(screen.getByRole("group", { name: "Highlight" })).toBeTruthy();
  });

  it("delete_needs_a_second_press", async () => {
    api.deleteHighlight.mockResolvedValue(null);
    const { container, onChanged } = setup({ highlights: [row()] });
    fireEvent.click(container.querySelector("mark"));
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(api.deleteHighlight).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
    await waitFor(() => expect(api.deleteHighlight).toHaveBeenCalledWith(7));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith([]));
    expect(logged.some((e) => e.type === "highlight_deleted")).toBe(true);
  });

  it("escape_closes_the_bar_and_returns_focus_to_the_text", () => {
    const { container } = setup();
    select(firstText(container), 0, 5);
    const bar = screen.getByRole("group", { name: "Highlight" });
    fireEvent.keyDown(bar, { key: "Escape" });
    expect(screen.queryByRole("group", { name: "Highlight" })).toBeNull();
    expect(document.activeElement).toBe(container.querySelector("[data-highlight-text]"));
  });

  it("alt_h_moves_focus_into_the_bar", () => {
    const { container } = setup();
    select(firstText(container), 0, 5);
    fireEvent.keyDown(document, { key: "h", altKey: true });
    const bar = screen.getByRole("group", { name: "Highlight" });
    expect(bar.contains(document.activeElement)).toBe(true);
  });

  it("alt_h_does_nothing_without_a_selection", () => {
    setup();
    fireEvent.keyDown(document, { key: "h", altKey: true });
    expect(screen.queryByRole("group", { name: "Highlight" })).toBeNull();
  });

  it("stale_highlight_is_not_drawn", () => {
    const { container } = setup({ highlights: [row({ quote: "Jello" })] });
    expect(container.querySelector("mark")).toBeNull();
    expect(container.textContent).toContain("Hello world.");
  });

  it("every_mark_names_its_colour_for_screen_readers_and_hover", () => {
    const { container } = setup({ highlights: [row({ color: "orange" })] });
    const mark = container.querySelector("mark");
    expect(mark.getAttribute("aria-label")).toMatch(/Orange/);
    expect(mark.getAttribute("title")).toMatch(/Orange/);
    expect(mark.tabIndex).toBe(0);
  });

  it("focus_highlight_id_scrolls_and_focuses_once", () => {
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    const { container, rerender, onChanged } = setup({ highlights: [row()], focusHighlightId: 7 });
    const mark = container.querySelector("mark[data-highlight-id='7']");
    expect(document.activeElement).toBe(mark);
    expect(scroll).toHaveBeenCalledTimes(1);
    rerender(
      <HighlightableText
        text={TEXT}
        bookId={2}
        microSessionId={11}
        enabled
        highlights={[row({ color: "blue" })]}
        onChanged={onChanged}
        focusHighlightId={7}
      />
    );
    expect(scroll).toHaveBeenCalledTimes(1);
    delete Element.prototype.scrollIntoView;
  });

  describe("merged blocks and stale ranges", () => {
    const TWO = (
      <>
        <HighlightableText text="First part text here." bookId={2} microSessionId={1} enabled highlights={[]} onChanged={vi.fn()} />
        <HighlightableText text="Second part text here." bookId={2} microSessionId={2} enabled highlights={[]} onChanged={vi.fn()} />
      </>
    );
    const bars = () => screen.queryAllByRole("group", { name: "Highlight" });

    it("only_one_bar_across_parts", () => {
      const { container } = render(TWO);
      const [a, b] = container.querySelectorAll("p");
      select(a.firstChild, 0, 5);
      expect(bars()).toHaveLength(1);
      select(b.firstChild, 0, 6);
      expect(bars()).toHaveLength(1);
    });

    it("selection_spanning_two_parts_shows_no_bar_and_clears_the_old_one", () => {
      const { container } = render(TWO);
      const [a, b] = container.querySelectorAll("p");
      select(a.firstChild, 0, 5);
      const range = document.createRange();
      range.setStart(a.firstChild, 2);
      range.setEnd(b.firstChild, 4);
      window.getSelection().removeAllRanges();
      window.getSelection().addRange(range);
      act(() => {
        document.dispatchEvent(new Event("selectionchange"));
      });
      expect(bars()).toHaveLength(0);
    });

    it("a_selection_that_becomes_too_long_clears_the_pending_range", () => {
      const long = "word ".repeat(600);
      const { container } = setup({ text: long });
      const node = container.querySelector("p").firstChild;
      select(node, 0, 5);
      expect(bars()).toHaveLength(1);
      select(node, 0, 2500);
      expect(bars()).toHaveLength(0);
    });

    it("a_collapsed_selection_keeps_the_bar_so_tapping_it_still_works", () => {
      const { container } = setup();
      select(firstText(container), 0, 5);
      window.getSelection().removeAllRanges();
      act(() => {
        document.dispatchEvent(new Event("selectionchange"));
      });
      expect(bars()).toHaveLength(1);
    });
  });

  it("escape_anywhere_closes_the_bar_and_focuses_the_text", () => {
    const { container } = setup();
    select(firstText(container), 0, 5);
    expect(document.activeElement).toBe(document.body);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("group", { name: "Highlight" })).toBeNull();
    expect(document.activeElement).toBe(container.querySelector("[data-highlight-text]"));
  });

  it("focus_returns_to_the_text_after_saving_and_after_deleting", async () => {
    api.createHighlight.mockResolvedValue(row({ id: 5 }));
    const { container, onChanged } = setup();
    select(firstText(container), 0, 5);
    const pink = screen.getByRole("button", { name: "Pink" });
    pink.focus();
    fireEvent.click(pink);
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(document.activeElement).toBe(container.querySelector("[data-highlight-text]"));

    api.deleteHighlight.mockResolvedValue(null);
    cleanup();
    const second = setup({ highlights: [row()] });
    fireEvent.click(second.container.querySelector("mark"));
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    const confirm = screen.getByRole("button", { name: "Confirm delete" });
    confirm.focus();
    fireEvent.click(confirm);
    await waitFor(() => expect(second.onChanged).toHaveBeenCalledWith([]));
    expect(document.activeElement).toBe(second.container.querySelector("[data-highlight-text]"));
  });

  it("on_focused_is_called_once_so_the_deep_link_does_not_refire", () => {
    Element.prototype.scrollIntoView = vi.fn();
    const onFocused = vi.fn();
    setup({ highlights: [row()], focusHighlightId: 7, onFocused });
    expect(onFocused).toHaveBeenCalledTimes(1);
    delete Element.prototype.scrollIntoView;
  });

  it("clicking_plain_text_closes_the_edit_bar_so_it_stops_covering_the_page", () => {
    const { container } = setup({ highlights: [row()] });
    fireEvent.click(container.querySelector("mark"));
    expect(screen.getByRole("group", { name: "Highlight" })).toBeTruthy();
    fireEvent.pointerDown(container.querySelector("[data-highlight-text] p"));
    expect(screen.queryByRole("group", { name: "Highlight" })).toBeNull();
  });

  it("clicking_inside_the_edit_bar_keeps_it_open", () => {
    const { container } = setup({ highlights: [row()] });
    fireEvent.click(container.querySelector("mark"));
    fireEvent.pointerDown(screen.getByLabelText("Comment (optional)"));
    expect(screen.getByRole("group", { name: "Highlight" })).toBeTruthy();
  });

  it("a_comment_typed_for_one_selection_does_not_carry_to_the_next", () => {
    const { container } = setup();
    const node = firstText(container);
    select(node, 0, 5);
    fireEvent.change(screen.getByLabelText("Comment (optional)"), { target: { value: "draft thought" } });
    select(node, 6, 11);
    expect(screen.getByLabelText("Comment (optional)").value).toBe("");
  });

  it("the_same_selection_keeps_its_draft_comment", () => {
    const { container } = setup();
    const node = firstText(container);
    select(node, 0, 5);
    fireEvent.change(screen.getByLabelText("Comment (optional)"), { target: { value: "draft thought" } });
    select(node, 0, 5);
    expect(screen.getByLabelText("Comment (optional)").value).toBe("draft thought");
  });
});

describe("citing from the edit bar", () => {
  const book = {
    title: "Alice",
    author: "Carroll, Lewis",
    published_year: 1865,
    gutenberg_id: 11,
    is_user_uploaded: false,
  };
  const withBook = (props) =>
    render(
      <SettingsProvider>
        <HighlightableText
          text={TEXT}
          bookId={2}
          microSessionId={11}
          enabled
          highlights={[row({ chapter_index: 1, chapter_title: "Chapter 1" })]}
          onChanged={vi.fn()}
          book={book}
          {...props}
        />
      </SettingsProvider>
    );

  it("an_existing_highlight_can_be_cited_when_the_book_is_known", () => {
    const { container } = withBook();
    fireEvent.click(container.querySelector("mark"));
    expect(screen.getByRole("button", { name: "Copy quote with citation" })).toBeTruthy();
    expect(screen.getByLabelText("Citation style")).toBeTruthy();
  });

  it("creating_a_new_highlight_shows_no_cite_options_yet", () => {
    const { container } = withBook({ highlights: [] });
    select(firstText(container), 6, 11);
    expect(screen.getByRole("group", { name: "Highlight" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Copy quote with citation" })).toBeNull();
  });

  it("without_book_details_nothing_about_citing_appears", () => {
    const { container } = withBook({ book: undefined });
    fireEvent.click(container.querySelector("mark"));
    expect(screen.queryByRole("button", { name: "Copy quote with citation" })).toBeNull();
  });
});
