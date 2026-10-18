// @vitest-environment jsdom
import { describe, it, expect, beforeEach } from "vitest";
import {
  toCodePointOffset,
  toUtf16Offset,
  paragraphStarts,
  selectionToRange,
  splitSegments,
  isStale,
} from "./positions";
import { MAX_SELECTION } from "./constants";

const cpSlice = (text, a, b) => Array.from(text).slice(a, b).join("");

// Render paragraphs the way HighlightableText does: <p data-start> with text.
function render(text, marks = []) {
  const container = document.createElement("div");
  for (const para of paragraphStarts(text)) {
    const p = document.createElement("p");
    p.dataset.start = String(para.start);
    for (const seg of splitSegments(text, para, marks)) {
      if (seg.highlight) {
        const m = document.createElement("mark");
        m.textContent = seg.text;
        p.appendChild(m);
      } else {
        p.appendChild(document.createTextNode(seg.text));
      }
    }
    container.appendChild(p);
  }
  document.body.appendChild(container);
  return container;
}

function selecting(startNode, startOffset, endNode, endOffset) {
  const range = document.createRange();
  range.setStart(startNode, startOffset);
  range.setEnd(endNode, endOffset);
  return { rangeCount: 1, isCollapsed: range.collapsed, getRangeAt: () => range };
}

beforeEach(() => {
  document.body.innerHTML = "";
});

describe("code points", () => {
  const text = "a\u{1F600}b\u{20BB7}c";
  it("code_point_conversion_round_trips_with_astral_chars", () => {
    expect(toCodePointOffset(text, 0)).toBe(0);
    expect(toCodePointOffset(text, 3)).toBe(2); // after the emoji (2 UTF-16 units)
    expect(toCodePointOffset(text, text.length)).toBe(5);
    for (let cp = 0; cp <= 5; cp++) expect(toCodePointOffset(text, toUtf16Offset(text, cp))).toBe(cp);
    expect(toUtf16Offset(text, 5)).toBe(text.length);
  });
});

describe("paragraphStarts", () => {
  it("paragraph_starts_match_split_on_blank_lines", () => {
    const text = "One two.\n\nThree\n\n\n\nFour";
    const paras = paragraphStarts(text);
    expect(paras.map((p) => p.text)).toEqual(text.split(/\n{2,}/));
    for (const p of paras) expect(cpSlice(text, p.start, p.start + Array.from(p.text).length)).toBe(p.text);
  });
  it("paragraph_starts_count_astral_characters_as_one", () => {
    const text = "\u{1F600} first\n\nsecond";
    expect(paragraphStarts(text)[1].start).toBe(Array.from("\u{1F600} first\n\n").length);
  });
  it("leading_separator_gives_an_empty_first_paragraph_like_the_reader", () => {
    expect(paragraphStarts("\n\nabc").map((p) => p.text)).toEqual("\n\nabc".split(/\n{2,}/));
  });
});

describe("selectionToRange", () => {
  const text = "Hello world.\n\nSecond paragraph here.";

  it("selection_within_one_paragraph", () => {
    const c = render(text);
    const node = c.children[0].firstChild;
    expect(selectionToRange(selecting(node, 6, node, 11), c, text)).toEqual({ start: 6, end: 11 });
  });

  it("selection_across_two_paragraphs", () => {
    const c = render(text);
    const a = c.children[0].firstChild;
    const b = c.children[1].firstChild;
    const r = selectionToRange(selecting(a, 6, b, 6), c, text);
    expect(cpSlice(text, r.start, r.end)).toBe("world.\n\nSecond");
  });

  it("selection_inside_an_existing_mark", () => {
    const hl = { id: 1, start: 0, end: 5, quote: "Hello" };
    const c = render(text, [hl]);
    const p = c.children[0];
    expect(p.querySelector("mark").textContent).toBe("Hello");
    const markText = p.querySelector("mark").firstChild;
    const tail = p.lastChild;
    // from inside the mark to the end of "world"
    expect(selectionToRange(selecting(markText, 2, tail, 6), c, text)).toEqual({ start: 2, end: 11 });
  });

  it("selection_with_astral_characters_before_it", () => {
    const t = "\u{1F600}\u{1F600} Hello there";
    const c = render(t);
    const node = c.children[0].firstChild;
    const u16Start = t.indexOf("Hello");
    const r = selectionToRange(selecting(node, u16Start, node, u16Start + 5), c, t);
    expect(r).toEqual({ start: 3, end: 8 });
    expect(cpSlice(t, r.start, r.end)).toBe("Hello");
  });

  it("selection_trims_surrounding_whitespace", () => {
    const c = render(text);
    const node = c.children[0].firstChild;
    expect(selectionToRange(selecting(node, 5, node, 12), c, text)).toEqual({ start: 6, end: 12 });
  });

  it("selection_ending_at_the_start_of_the_next_paragraph_stops_at_the_text", () => {
    const c = render(text);
    const a = c.children[0].firstChild;
    const b = c.children[1].firstChild;
    expect(selectionToRange(selecting(a, 0, b, 0), c, text)).toEqual({ start: 0, end: 12 });
  });

  it("selection_outside_container_or_collapsed_or_too_long_is_null", () => {
    const c = render(text);
    const outside = document.createElement("p");
    outside.textContent = "elsewhere";
    document.body.appendChild(outside);
    const node = c.children[0].firstChild;
    expect(selectionToRange(selecting(node, 2, node, 2), c, text)).toBeNull();
    expect(selectionToRange(selecting(outside.firstChild, 0, outside.firstChild, 4), c, text)).toBeNull();
    expect(selectionToRange(selecting(outside.firstChild, 0, outside.firstChild, 4), c, text)).toBeNull();
    expect(selectionToRange({ rangeCount: 0 }, c, text)).toBeNull();

    const long = "x".repeat(MAX_SELECTION + 5);
    const c2 = render(long);
    const n2 = c2.lastChild.firstChild;
    expect(selectionToRange(selecting(n2, 0, n2, MAX_SELECTION + 1), c2, long)).toBeNull();
    expect(selectionToRange(selecting(n2, 0, n2, MAX_SELECTION), c2, long)).toEqual({
      start: 0,
      end: MAX_SELECTION,
    });
  });

  it("triple_click_ending_on_the_container_or_after_it_still_selects_the_paragraph", () => {
    const t = text;
    const c = render(t);
    const last = c.children[1].firstChild;
    // end boundary is (container, childCount): what browsers report after a triple-click on the last paragraph
    expect(selectionToRange(selecting(last, 0, c, c.childNodes.length), c, t)).toEqual({
      start: 14,
      end: Array.from(t).length,
    });
    // end boundary lands in the next block, outside the container
    const after = document.createElement("div");
    after.textContent = "footer";
    document.body.appendChild(after);
    expect(selectionToRange(selecting(last, 0, after.firstChild, 0), c, t)).toEqual({
      start: 14,
      end: Array.from(t).length,
    });
  });

  it("selection_starting_before_the_container_starts_at_the_first_character", () => {
    const t = "Hello world.";
    const c = render(t);
    const before = document.createElement("div");
    before.textContent = "header";
    document.body.insertBefore(before, c);
    const node = c.children[0].firstChild;
    expect(selectionToRange(selecting(before.firstChild, 2, node, 5), c, t)).toEqual({ start: 0, end: 5 });
  });

  it("whitespace_only_selection_is_null", () => {
    const t = "ab   cd";
    const c = render(t);
    const node = c.children[0].firstChild;
    expect(selectionToRange(selecting(node, 2, node, 5), c, t)).toBeNull();
  });
});

describe("splitSegments", () => {
  const text = "Hello world.\n\nSecond paragraph here.";
  const [p1, p2] = paragraphStarts(text);
  const hl = (id, start, end) => ({ id, start, end, quote: cpSlice(text, start, end) });

  it("split_segments_plain_when_no_highlights", () => {
    expect(splitSegments(text, p1, [])).toEqual([{ text: "Hello world.", highlight: null }]);
  });

  it("split_segments_marks_the_range_and_reassembles_to_the_text", () => {
    const h = hl(1, 6, 11);
    const segs = splitSegments(text, p1, [h]);
    expect(segs.map((s) => s.text).join("")).toBe(p1.text);
    expect(segs.filter((s) => s.highlight).map((s) => [s.text, s.highlight.id])).toEqual([["world", 1]]);
    expect(segs.every((s) => s.text.length > 0)).toBe(true);
  });

  it("split_segments_two_in_one_paragraph_and_one_spanning_paragraphs", () => {
    const a = hl(1, 0, 5);
    const b = hl(2, 6, 11);
    const spanning = hl(3, 8, p2.start + 6); // "rld." through "Second"
    const first = splitSegments(text, p1, [a, spanning]);
    expect(first.map((s) => s.text).join("")).toBe(p1.text);
    expect(first.filter((s) => s.highlight).map((s) => s.highlight.id)).toEqual([1, 3]);
    const second = splitSegments(text, p2, [spanning]);
    expect(second.map((s) => s.text).join("")).toBe(p2.text);
    expect(second[0].highlight.id).toBe(3);
    expect(second[0].text.length).toBeGreaterThan(0);
    const both = splitSegments(text, p1, [a, b]);
    expect(both.filter((s) => s.highlight).map((s) => s.text)).toEqual(["Hello", "world"]);
  });

  it("split_segments_counts_code_points_after_astral_characters", () => {
    const t = "\u{1F600} Hello there";
    const [p] = paragraphStarts(t);
    const h = { id: 1, start: 2, end: 7, quote: "Hello" };
    const segs = splitSegments(t, p, [h]);
    expect(segs.map((s) => s.text)).toEqual(["\u{1F600} ", "Hello", " there"]);
    expect(segs[1].highlight.id).toBe(1);
  });

  it("stale_highlight_is_not_drawn_and_is_reported_stale", () => {
    const stale = { id: 9, start: 0, end: 5, quote: "Jello" };
    expect(isStale(text, stale)).toBe(true);
    expect(isStale(text, hl(1, 0, 5))).toBe(false);
    expect(splitSegments(text, p1, [stale])).toEqual([{ text: "Hello world.", highlight: null }]);
    expect(isStale(text, { id: 2, start: 0, end: 9999, quote: "x" })).toBe(true);
  });

  it("overlapping_stored_highlights_never_duplicate_text", () => {
    const segs = splitSegments(text, p1, [hl(1, 0, 8), hl(2, 5, 11)]);
    expect(segs.map((s) => s.text).join("")).toBe(p1.text);
  });
});
