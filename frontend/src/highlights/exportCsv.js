import { citation, chapterLocator, toPlain } from "../citations/format";
import { colorLabel } from "./constants";

const HEADER = ["book", "author", "chapter", "chapter_title", "quote", "comment", "colour", "themes", "citation", "created"];

// A spreadsheet runs a cell that starts with one of these as a formula, so a
// note (or a book title) cannot be allowed to begin with them.
const FORMULA_START = /^[\t\r]|^\s*[=+\-@]/;

function cell(value) {
  let text = String(value ?? "");
  if (FORMULA_START.test(text)) text = `'${text}`;
  return `"${text.replace(/"/g, '""')}"`;
}

export function notesCsvFileName(bookTitle) {
  const cleaned = String(bookTitle ?? "")
    .replace(/[\\/:*?"<>|]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return `${cleaned || "Book"} - notes.csv`;
}

/** One row per note, in reading order, with its citation and passage themes. */
export function buildNotesCsv({ book, style, highlights }) {
  const ordered = [...highlights].sort(
    (a, b) =>
      a.chapter_index - b.chapter_index || a.session_index - b.session_index || a.start - b.start
  );
  const lines = [HEADER.join(",")];
  for (const h of ordered) {
    const c = citation(style, book, h);
    lines.push(
      [
        book.title,
        book.author,
        chapterLocator(h).label,
        h.chapter_title,
        h.quote,
        h.comment,
        colorLabel(h.color),
        (h.themes || []).map((t) => t.label).join("; "),
        toPlain(c.inText || c.footnote),
        h.created_at,
      ]
        .map(cell)
        .join(",")
    );
  }
  return lines.join("\r\n") + "\r\n";
}
