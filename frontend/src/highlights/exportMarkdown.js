import { chapterLocator, citation, toMarkdown } from "../citations/format";
import { colorLabel } from "./constants";

export function notesFileName(bookTitle) {
  const cleaned = String(bookTitle ?? "")
    .replace(/[\\/:*?"<>|]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return `${cleaned || "Book"} - notes.md`;
}

const unix = (text) => String(text).replace(/\r\n?/g, "\n");

const quoteBlock = (text) =>
  unix(text)
    .split("\n")
    .map((line) => (line ? `> ${line}` : "> "))
    .join("\n");

// A comment is the reader's own words: stop a line that begins with #, >, a
// bullet or "1." from turning into a heading, quote or list.
function escapeLine(line) {
  if (/^\s*(-{3,}|={3,})\s*$/.test(line)) return line.replace(/^(\s*)/, "$1\\");
  if (/^\s*[#>]/.test(line) || /^\s*[-+*]\s/.test(line)) return line.replace(/^(\s*)/, "$1\\");
  return line.replace(/^(\s*\d+)([.)])(\s)/, "$1\\$2$3");
}
const commentBlock = (text) => unix(text).split("\n").map(escapeLine).join("\n");

export const chapterHeading = (h) => h.chapter_title || chapterLocator(h).label;

export function buildNotesMarkdown({ bookTitle, highlights, book = null, style = "apa" }) {
  const ordered = [...highlights].sort(
    (a, b) =>
      a.chapter_index - b.chapter_index || a.session_index - b.session_index || a.start - b.start
  );
  const lines = [`# ${bookTitle || "Book"}`, ""];
  let chapter = null;
  for (const h of ordered) {
    if (h.chapter_index !== chapter) {
      chapter = h.chapter_index;
      lines.push(`## ${chapterHeading(h)}`, "");
    }
    lines.push(quoteBlock(h.quote), "");
    if (book) {
      const c = citation(style, book, h);
      lines.push(toMarkdown(c.inText || c.footnote), "");
    }
    let meta = h.session_number ? `${colorLabel(h.color)} · Session ${h.session_number}` : colorLabel(h.color);
    if (book && h.themes?.length) meta += ` · Themes: ${h.themes.map((t) => t.label).join(", ")}`;
    lines.push(meta, "");
    if (h.comment) lines.push(commentBlock(h.comment), "");
  }
  if (book && ordered.length) {
    lines.push("## Reference", "", toMarkdown(citation(style, book, ordered[0]).reference), "");
  }
  return lines.join("\n");
}
