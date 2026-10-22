/**
 * Citations for passages of a book, in APA 7, MLA 9 and Chicago 17
 * (notes-bibliography). Pure functions: text in, text out.
 *
 * A citation is a list of parts, {text, italic?}, so the same result can be
 * rendered as plain text, Markdown or HTML. The locator is always the chapter
 * (ebooks have no stable page numbers). Titles are used as stored.
 */

export const STYLES = ["apa", "mla", "chicago"];

const SOURCE = "Project Gutenberg";
const ROMAN = { i: 1, v: 5, x: 10, l: 50, c: 100, d: 500, m: 1000 };

// Exported so the research citations can build the same {text, italic} parts
// and render through the same toPlain/toMarkdown/toHtml.
export const part = (text, italic = false) => (italic ? { text, italic: true } : { text });
const fromRoman = (s) => {
  let total = 0;
  const digits = [...s.toLowerCase()].map((c) => ROMAN[c]);
  digits.forEach((v, i) => {
    total += digits[i + 1] > v ? -v : v;
  });
  return total;
};

const SUFFIX = /^(jr|sr|ii|iii|iv)\.?$/i;

export function parseAuthor(name) {
  // "Twain, Mark (Samuel Clemens)": the bracketed real name is not part of the citation.
  const text = String(name ?? "").replace(/\s*\([^)]*\)/g, "").trim();
  if (!text || /^unknown$/i.test(text)) return { unknown: true, last: "", given: "", single: false };
  const comma = text.indexOf(",");
  if (comma < 0) {
    // "Voltaire" is a single name. "Jane Doe", as typed in an upload form, is
    // given name(s) then surname.
    const words = text.split(/\s+/);
    if (words.length === 1) return { unknown: false, last: text, given: "", single: true };
    return { unknown: false, last: words[words.length - 1], given: words.slice(0, -1).join(" "), single: false };
  }
  const last = text.slice(0, comma).trim();
  // "Doe, Jane, Jr.": a generational suffix is not a given name.
  const given = text
    .slice(comma + 1)
    .split(",")
    .map((piece) => piece.trim())
    .filter((piece) => piece && !SUFFIX.test(piece))
    .join(" ");
  if (!given) return { unknown: false, last, given: "", single: true };
  return { unknown: false, last, given, single: false };
}

export const initials = (given) =>
  given
    .split(/\s+/)
    .filter(Boolean)
    .map((word) =>
      word
        .split("-")
        .filter(Boolean)
        .map((piece) => `${piece[0].toUpperCase()}.`)
        .join("-")
    )
    .join(" ");

// A proper roman numeral, written in one case ("XIV" or "xiv", never "Mix").
const ROMAN_NUMERAL = /^(?=[ivxlcdm])m{0,3}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$/i;
const isRoman = (word) => ROMAN_NUMERAL.test(word) && (word === word.toUpperCase() || word === word.toLowerCase());

/**
 * Where in the book a passage is, for a citation. "CHAPTER I. THE RABBIT-HOLE"
 * and "Chapter 5" give a chapter number; any other title is used as it is; an
 * untitled chapter (the lead-in before chapter 1) gets a plain label and never a
 * number it may not have.
 */
export function chapterLocator({ chapter_title: title, chapter_index: index }) {
  const text = String(title ?? "").trim();
  const match = /^chapter\s+([^\s.:\-\u2013\u2014]+)(?:[.:\s\-\u2013\u2014]|$)/i.exec(text);
  if (match) {
    const raw = match[1];
    const number = /^\d+$/.test(raw) ? parseInt(raw, 10) : isRoman(raw) ? fromRoman(raw) : null;
    if (number) return { number, label: `Chapter ${number}`, generic: false };
  }
  if (text) return { number: null, label: text, generic: false };
  const at = index ?? 0;
  return { number: null, label: at === 0 ? "Opening section" : `Section ${at + 1}`, generic: true };
}

const titleEnd = (title) => (/[.?!]$/.test(title) ? "" : ".");
const shortTitle = (title) => title.split(/[:;]/)[0].trim();
const quoted = (text) => `“${text}”`;

function facts(book) {
  const author = parseAuthor(book.author);
  const url = !book.is_user_uploaded && book.gutenberg_id ? `https://www.gutenberg.org/ebooks/${book.gutenberg_id}` : null;
  return {
    author,
    title: book.title || "Untitled",
    year: book.published_year ? String(book.published_year) : null,
    url,
    upload: Boolean(book.is_user_uploaded),
  };
}

const withTrailingPeriod = (text) => (/[.?!]$/.test(text) ? text : `${text}.`);

function apa(f, loc) {
  const year = `(${f.year ?? "n.d."})`;
  const names = f.author.unknown ? null : f.author.single ? `${f.author.last}.` : `${f.author.last}, ${initials(f.author.given)}`;
  const reference = [];
  if (names) reference.push(part(`${names} ${year}. `), part(f.title, true));
  else reference.push(part(f.title, true), part(`${titleEnd(f.title)} ${year}.`));
  if (f.url) reference.push(part(`${names ? titleEnd(f.title) : ""} ${SOURCE}. ${f.url}`));
  else if (f.upload) reference.push(part(" [Uploaded file]."));
  const where = loc.number != null || loc.generic ? loc.label : quoted(loc.label);
  const who = f.author.unknown ? quoted(shortTitle(f.title)) : f.author.last;
  return { reference, inText: [part(`(${who}, ${f.year ?? "n.d."}, ${where})`)], footnote: null };
}

function bibliography(f) {
  const names = f.author.unknown
    ? null
    : f.author.single
      ? withTrailingPeriod(f.author.last)
      : withTrailingPeriod(`${f.author.last}, ${f.author.given}`);
  const out = [];
  if (names) out.push(part(`${names} `));
  out.push(part(f.title, true), part(`${titleEnd(f.title)} `));
  if (f.year) out.push(part(`${f.year}. `));
  return out;
}

function mla(f, loc) {
  const reference = bibliography(f);
  if (f.url) reference.push(part(SOURCE, true), part(`, ${f.url.replace(/^https?:\/\//, "")}.`));
  else if (f.upload) reference.push(part("Uploaded file."));
  else reference[reference.length - 1] = part(reference[reference.length - 1].text.trimEnd());
  const where = loc.number != null ? `ch. ${loc.number}` : loc.generic ? loc.label : quoted(loc.label);
  const who = f.author.unknown ? quoted(shortTitle(f.title)) : f.author.last;
  return { reference, inText: [part(`(${who}, ${where})`)], footnote: null };
}

function chicago(f, loc) {
  const reference = bibliography(f);
  if (f.url) reference.push(part(`${SOURCE}. ${f.url}.`));
  else if (f.upload) reference.push(part("Uploaded file."));
  else reference[reference.length - 1] = part(reference[reference.length - 1].text.trimEnd());

  const name = f.author.unknown ? null : f.author.single ? f.author.last : `${f.author.given} ${f.author.last}`;
  const note = [];
  if (name) note.push(part(`${name}, `));
  note.push(part(f.title, true));
  const paren = [f.year, f.url ? SOURCE : f.upload ? "uploaded file" : null].filter(Boolean).join("; ");
  const tail =
    loc.number != null
      ? `, chap. ${loc.number}.`
      : loc.generic
        ? `, ${loc.label.toLowerCase()}.`
        : `, ${quoted(withTrailingPeriod(loc.label))}`;
  note.push(part(`${paren ? ` (${paren})` : ""}${tail}`));
  return { reference, inText: null, footnote: note };
}

export function citation(style, book, highlight) {
  const f = facts(book);
  const loc = chapterLocator(highlight);
  if (style === "mla") return mla(f, loc);
  if (style === "chicago") return chicago(f, loc);
  return apa(f, loc);
}

export const toPlain = (parts) => parts.map((p) => p.text).join("");
export const toMarkdown = (parts) => parts.map((p) => (p.italic ? `*${p.text}*` : p.text)).join("");

const escapeHtml = (text) =>
  text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
export const toHtml = (parts) =>
  parts.map((p) => (p.italic ? `<i>${escapeHtml(p.text)}</i>` : escapeHtml(p.text))).join("");
