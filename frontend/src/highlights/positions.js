import { MAX_SELECTION } from "./constants";

// All highlight positions are Unicode code points into the micro-session text,
// matching the server (Python indexes strings by code point). The browser
// counts UTF-16 units, so these helpers convert at the edge.

// One passage is read over and over (every highlight, every paragraph), so
// keep the most recent code point array instead of rebuilding it each time.
let cachedText = null;
let cachedChars = [];
function codePoints(text) {
  if (text !== cachedText) {
    cachedText = text;
    cachedChars = Array.from(text);
  }
  return cachedChars;
}

export function toCodePointOffset(text, utf16Index) {
  return Array.from(text.slice(0, utf16Index)).length;
}

export function toUtf16Offset(text, cpIndex) {
  let units = 0;
  let count = 0;
  for (const ch of text) {
    if (count >= cpIndex) break;
    units += ch.length;
    count += 1;
  }
  return units;
}

/** The paragraphs exactly as the Reader splits them, with code point starts. */
export function paragraphStarts(text) {
  const out = [];
  let from = 0;
  for (const m of text.matchAll(/\n{2,}/g)) {
    out.push({ text: text.slice(from, m.index), start: toCodePointOffset(text, from) });
    from = m.index + m[0].length;
  }
  out.push({ text: text.slice(from), start: toCodePointOffset(text, from) });
  return out;
}

function paragraphOf(node, container) {
  const el = node.nodeType === 1 ? node : node.parentElement;
  const p = el?.closest?.("p[data-start]");
  return p && container.contains(p) ? p : null;
}

// Code point position of (node, offset) in the whole micro-session text.
function positionOf(node, offset, container, total) {
  if (node === container) {
    // A boundary on the container itself (offset counts child paragraphs).
    const child = container.children[offset];
    return child ? Number(child.dataset.start) : total;
  }
  const p = paragraphOf(node, container);
  if (!p) return null;
  const range = document.createRange();
  range.selectNodeContents(p);
  range.setEnd(node, offset);
  const before = range.toString();
  return Number(p.dataset.start) + Array.from(before).length;
}

// Another highlightable passage on the page (a later part of a merged block).
function inOtherPart(node, container) {
  const el = node.nodeType === 1 ? node : node.parentElement;
  const host = el?.closest?.("[data-highlight-text]");
  return Boolean(host && host !== container);
}

/**
 * Turn the browser selection into {start, end} code points, trimmed of
 * surrounding whitespace, or null when it is empty, collapsed, longer than
 * MAX_SELECTION, or reaches into another passage. A boundary just outside the
 * container (a triple-click usually ends in the next block) is clamped to the
 * passage edge.
 */
export function selectionToRange(selection, container, text) {
  if (!selection || !selection.rangeCount || selection.isCollapsed) return null;
  const range = selection.getRangeAt(0);
  const startInside = container.contains(range.startContainer);
  const endInside = container.contains(range.endContainer);
  if (!startInside && !endInside) return null;
  if (!startInside && inOtherPart(range.startContainer, container)) return null;
  if (!endInside && inOtherPart(range.endContainer, container)) return null;

  const chars = codePoints(text);
  let start = startInside ? positionOf(range.startContainer, range.startOffset, container, chars.length) : 0;
  let end = endInside ? positionOf(range.endContainer, range.endOffset, container, chars.length) : chars.length;
  if (start === null || end === null || end <= start) return null;

  while (start < end && /\s/.test(chars[start])) start += 1;
  while (end > start && /\s/.test(chars[end - 1])) end -= 1;
  if (end <= start || end - start > MAX_SELECTION) return null;
  return { start, end };
}

export function isStale(fullText, highlight) {
  const chars = codePoints(fullText);
  if (highlight.end > chars.length || highlight.start < 0) return true;
  return chars.slice(highlight.start, highlight.end).join("") !== highlight.quote;
}

/**
 * Cut one paragraph into plain and highlighted pieces. Highlights whose stored
 * quote no longer matches the text are skipped; overlapping ones never repeat
 * text. Pieces joined together always equal the paragraph.
 */
export function splitSegments(fullText, paragraph, highlights) {
  const chars = Array.from(paragraph.text);
  const pStart = paragraph.start;
  const pEnd = pStart + chars.length;

  const cuts = highlights
    .filter((h) => !isStale(fullText, h))
    .map((h) => ({ h, from: Math.max(h.start, pStart), to: Math.min(h.end, pEnd) }))
    .filter((c) => c.from < c.to)
    .sort((a, b) => a.from - b.from);

  const out = [];
  let cursor = pStart;
  for (const { h, from, to } of cuts) {
    if (from < cursor) continue; // overlaps one already drawn
    if (from > cursor) out.push({ text: chars.slice(cursor - pStart, from - pStart).join(""), highlight: null });
    out.push({ text: chars.slice(from - pStart, to - pStart).join(""), highlight: h });
    cursor = to;
  }
  if (cursor < pEnd) out.push({ text: chars.slice(cursor - pStart).join(""), highlight: null });
  if (out.length === 0) out.push({ text: paragraph.text, highlight: null });
  return out;
}
