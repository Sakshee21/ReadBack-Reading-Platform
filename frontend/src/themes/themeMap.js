/**
 * Working out what a theme map should draw.
 *
 * Kept apart from the component because the awkward parts - how wide the
 * chart is, which chapters get a label, how a per-passage row collapses into
 * a per-chapter one - are arithmetic, and arithmetic is worth testing without
 * a DOM.
 *
 * None of this decides what the reader may see. The server sends only the
 * tags for passages the reader has reached; everything here reads that
 * response and lays it out. Widening the chart to the whole book therefore
 * cannot reveal anything, because there is nothing extra in hand to reveal.
 */

import { chapterLocator } from "../citations/format";

export const BY_PASSAGE = "passage";
export const BY_CHAPTER = "chapter";

export const READ_SO_FAR = "read";
export const WHOLE_BOOK = "whole";

// A passage square never gets narrower than this. Below about 6px a square is
// neither visible nor clickable, and squeezing is what made the old chart a
// row of hairlines.
export const MIN_CELL_PX = 7;
// Columns a chapter label needs to itself before the next one may appear.
// "Ch 12" at 0.7rem is about 34px, which is five columns at the minimum width.
export const MIN_LABEL_COLUMNS = 5;

/**
 * How many columns the chart covers.
 *
 * Reading so far fits the chart to the part of the book the reader has got
 * through, which is the whole point: a chart scaled to a 500-passage novel
 * when the reader is 20 passages in is 96% empty.
 */
export function columnCount({ total = 0, reached = 0, scale = READ_SO_FAR } = {}) {
  const whole = Math.max(0, Math.floor(total));
  if (scale === WHOLE_BOOK) return Math.max(1, whole);
  const read = Math.max(0, Math.floor(reached));
  // A missing or silly `reached` falls back to the whole book rather than
  // collapsing the chart to nothing.
  if (!read) return Math.max(1, whole);
  return Math.max(1, Math.min(read, whole || read));
}

/** The chapters that overlap the drawn range, clipped to it. */
export function chaptersInRange(chapters = [], columns) {
  const out = [];
  for (const chapter of chapters) {
    if (chapter.start >= columns) break;
    out.push({ ...chapter, end: Math.min(chapter.end, columns - 1) });
  }
  return out;
}

/**
 * Which chapters may carry a label, so that no two labels collide.
 *
 * Walks left to right and takes a chapter only once it is far enough past the
 * last one labelled. That thins evenly however uneven the chapters are, and
 * the first chapter is always labelled so the chart has an anchor.
 */
export function thinChapterLabels(chapters = [], { minColumns = MIN_LABEL_COLUMNS } = {}) {
  const gap = Math.max(1, minColumns);
  const out = [];
  let last = -Infinity;
  for (const chapter of chapters) {
    if (chapter.start - last >= gap) {
      out.push(chapter);
      last = chapter.start;
    }
  }
  return out;
}

/**
 * The short label for a chapter: its printed number where it has one, its
 * position in the book otherwise. Never the crushed title - that is what
 * turned a long book into a row of "C|C|C".
 */
export function shortChapterLabel(chapter, ordinal) {
  const { number } = chapterLocator({
    chapter_title: chapter?.title ?? "",
    chapter_index: chapter?.index ?? 0,
  });
  return `Ch ${number ?? ordinal}`;
}

/** The full title for a tooltip, falling back to the locator's wording. */
export function chapterTitle(chapter) {
  const title = (chapter?.title ?? "").trim();
  if (title) return title;
  return chapterLocator({ chapter_title: "", chapter_index: chapter?.index ?? 0 }).label;
}

/**
 * Collapse one theme row into a cell per chapter.
 *
 * The cell takes the strongest score anywhere in that chapter, which is what
 * makes a 500-passage book readable: a reader wants to see that Chapter 12 is
 * where the grief is, not which of its nine passages scored a 4.
 *
 * Chapters with no tag in them get no cell. That includes chapters the reader
 * has not reached, because the server sent no tags for those in the first
 * place.
 */
export function cellsByChapter(cells = [], chapters = []) {
  const strongest = new Map();
  for (const cell of cells) {
    const chapter = chapters.find((c) => c.start <= cell.pos && cell.pos <= c.end);
    if (!chapter) continue;
    const found = strongest.get(chapter.index);
    if (!found) {
      strongest.set(chapter.index, {
        chapter,
        score: cell.score,
        count: 1,
        micro_session_id: cell.micro_session_id,
        pos: cell.pos,
      });
      continue;
    }
    found.count += 1;
    if (cell.score > found.score) {
      found.score = cell.score;
      // Follow the link to the strongest passage, which is the one worth
      // opening.
      found.micro_session_id = cell.micro_session_id;
      found.pos = cell.pos;
    }
  }
  return chapters
    .map((chapter) => strongest.get(chapter.index))
    .filter(Boolean)
    .sort((a, b) => a.pos - b.pos);
}

/** Drop anything outside the drawn range. Belt and braces: in the default
 * scale the server has already held these back. */
export function cellsInRange(cells = [], columns) {
  return cells.filter((cell) => cell.pos < columns);
}
