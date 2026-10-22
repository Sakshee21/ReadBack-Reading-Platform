/**
 * Citations for research documents: journal articles and textbook chapters,
 * in APA 7, MLA 9 and Chicago 17 (notes-bibliography).
 *
 * Separate from citations/format.js because the shapes genuinely differ. A
 * novel is cited as a whole work located by chapter; an article is cited
 * inside a venue, and a textbook chapter inside a book. Both reuse the same
 * {text, italic} parts, so toPlain/toMarkdown/toHtml render either.
 *
 * Nothing here invents a field. A document with no year is cited "n.d.", a
 * document with no venue simply has no venue in its reference, and a document
 * with no authors is cited by title. That is the whole point of leaving the
 * extracted metadata blank rather than guessing it.
 */

import { initials, part } from "./format";

export const STYLES = ["apa", "mla", "chicago"];

const SUFFIX = /^(jr|sr|ii|iii|iv)\.?$/i;

/**
 * Split an authors field into names.
 *
 * Two conventions are in use and they are not distinguishable name by name, so
 * the separator decides: semicolons mean the pieces are "Surname, Given"
 * (how a form is usually filled in), anything else means they are given-first
 * ("A. Reader, B. Writer, and C. Editor", how a paper prints them).
 */
export function parseAuthorList(raw) {
  const text = String(raw ?? "")
    .replace(/\s*\([^)]*\)/g, "")
    .trim();
  if (!text || /^unknown$/i.test(text)) return [];

  const pieces = text.includes(";")
    ? text.split(";")
    : text.split(/,|\band\b|&/i);

  return pieces
    .map((piece) => piece.trim())
    .filter((piece) => piece && !SUFFIX.test(piece))
    .map((piece) => {
      if (text.includes(";") && piece.includes(",")) {
        const [last, ...rest] = piece.split(",");
        const given = rest.join(" ").trim();
        return { last: last.trim(), given, single: !given };
      }
      const words = piece.split(/\s+/).filter(Boolean);
      if (words.length === 1) return { last: words[0], given: "", single: true };
      return { last: words[words.length - 1], given: words.slice(0, -1).join(" "), single: false };
    })
    .filter((name) => name.last);
}

/**
 * Where in a document a passage is: the section, with its number when the
 * heading carries one ("III. METHOD" -> 3, "Chapter 2. ..." -> 2).
 */
export function sectionLocator({ title, kind, index } = {}) {
  const text = String(title ?? "").trim();
  if (kind === "abstract") return { label: "Abstract", number: null, generic: false };
  if (kind === "references") return { label: "References", number: null, generic: false };

  const roman = /^([IVXLCDM]{1,6})[.)]/.exec(text);
  const arabic = /^(?:chapter\s+)?(\d{1,2})(?:\.\d{1,2})*[.)\s]/i.exec(text);
  if (roman) return { label: text, number: fromRoman(roman[1]), generic: false };
  if (arabic) return { label: text, number: parseInt(arabic[1], 10), generic: false };
  if (text) return { label: text, number: null, generic: false };
  return { label: index ? `Section ${index + 1}` : "Opening section", number: null, generic: true };
}

const ROMAN = { i: 1, v: 5, x: 10, l: 50, c: 100, d: 500, m: 1000 };
function fromRoman(s) {
  const digits = [...s.toLowerCase()].map((c) => ROMAN[c]);
  return digits.reduce((total, v, i) => total + (digits[i + 1] > v ? -v : v), 0);
}

// Shown in place of a field the document did not state and nobody has filled
// in. The whole point is that a citation with a gap must look like one, so a
// wrong citation cannot be pasted into a paper unnoticed.
export const PLACEHOLDER = { authors: "[Author]", title: "[Title]", year: "[Year]" };

/** Which of the fields a citation cannot be written without are missing. */
export function missingForCitation(doc = {}) {
  const gaps = [];
  if (!String(doc.title ?? "").trim()) gaps.push("title");
  const authors = String(doc.authors ?? doc.author ?? "").trim();
  if (!authors || /^unknown$/i.test(authors)) gaps.push("authors");
  if (!doc.year && !doc.no_date) gaps.push("year");
  for (const field of doc.unverified ?? []) if (!gaps.includes(field)) gaps.push(field);
  return gaps;
}

/**
 * Is this a conference paper rather than a journal article?
 *
 * Read off the venue, because that is the only place a PDF says so. It
 * changes how the venue is introduced ("In Proceedings of...") and nothing
 * factual, so getting it wrong costs a preposition rather than a wrong claim.
 */
const CONFERENCE_VENUE =
  /\b(proc\.?|proceedings|conference|conf\.?|symposium|symp\.?|workshop|congress|annual meeting)\b/i;

export function isConference(venue) {
  return CONFERENCE_VENUE.test(String(venue ?? ""));
}

const quoted = (text) => `“${text}”`;
const period = (text) => (/[.?!]$/.test(text) ? text : `${text}.`);
const doiUrl = (doi) => (/^https?:\/\//i.test(doi) ? doi : `https://doi.org/${doi}`);

function facts(doc) {
  const authors = parseAuthorList(doc.authors ?? doc.author);
  const venue = (doc.venue || "").trim();
  const gaps = missingForCitation(doc);
  return {
    authors,
    isChapter: doc.doc_kind === "textbook",
    // A conference paper is cited inside its proceedings, the same shape as a
    // chapter inside a book.
    inProceedings: !doc.doc_kind || doc.doc_kind === "paper" ? isConference(venue) : false,
    // For an article the document title is the item; for a textbook the
    // document title is the container and the section is the item.
    documentTitle: doc.title || (gaps.includes("title") ? PLACEHOLDER.title : "Untitled document"),
    venue,
    // A missing year is only "n.d." once somebody has confirmed the document
    // has no date. Until then it is a gap, and it shows as one.
    year: doc.year ? String(doc.year) : doc.no_date ? "n.d." : PLACEHOLDER.year,
    doi: (doc.doi || "").trim(),
    gaps,
  };
}

// ---------------------------------------------------------------------------
// author name rendering, per style
// ---------------------------------------------------------------------------

const apaName = (n) => (n.single ? n.last : `${n.last}, ${initials(n.given)}`);

function apaAuthors(list) {
  if (!list.length) return null;
  if (list.length === 1) return apaName(list[0]);
  if (list.length <= 20) {
    const all = list.map(apaName);
    return `${all.slice(0, -1).join(", ")}, & ${all[all.length - 1]}`;
  }
  return `${list.slice(0, 19).map(apaName).join(", ")}, ... ${apaName(list[list.length - 1])}`;
}

function mlaAuthors(list) {
  if (!list.length) return null;
  const first = list[0].single ? list[0].last : `${list[0].last}, ${list[0].given}`;
  if (list.length === 1) return period(first);
  if (list.length === 2) {
    const second = list[1].single ? list[1].last : `${list[1].given} ${list[1].last}`;
    return period(`${first}, and ${second}`);
  }
  return period(`${first}, et al`);
}

function chicagoNoteAuthors(list) {
  if (!list.length) return null;
  const plain = (n) => (n.single ? n.last : `${n.given} ${n.last}`);
  if (list.length === 1) return plain(list[0]);
  if (list.length <= 3) {
    const all = list.map(plain);
    return `${all.slice(0, -1).join(", ")}, and ${all[all.length - 1]}`;
  }
  return `${plain(list[0])} et al.`;
}

function chicagoBibAuthors(list) {
  if (!list.length) return null;
  const first = list[0].single ? list[0].last : `${list[0].last}, ${list[0].given}`;
  if (list.length === 1) return period(first);
  const rest = list.slice(1).map((n) => (n.single ? n.last : `${n.given} ${n.last}`));
  if (list.length <= 3) {
    return period(`${first}, ${rest.length > 1 ? `${rest.slice(0, -1).join(", ")}, and ` : "and "}${rest[rest.length - 1]}`);
  }
  return period(`${first}, et al`);
}

// The short name used in an in-text citation.
function shortName(list, fallbackTitle, gaps = []) {
  if (!list.length && gaps.includes("authors")) return PLACEHOLDER.authors;
  if (!list.length) return quoted(fallbackTitle.split(/[:;]/)[0].trim());
  if (list.length === 1) return list[0].last;
  if (list.length === 2) return `${list[0].last} and ${list[1].last}`;
  return `${list[0].last} et al.`;
}

// ---------------------------------------------------------------------------
// styles
// ---------------------------------------------------------------------------

const where = (loc) => (loc.number != null ? `Section ${loc.number}` : loc.label);

function apa(f, loc) {
  const year = `(${f.year})`;
  const names = apaAuthors(f.authors) ?? (f.gaps.includes("authors") ? PLACEHOLDER.authors : null);
  const reference = [];

  if (f.inProceedings) {
    // A conference paper sits inside its proceedings, the same shape as a
    // chapter inside a book.
    if (names) reference.push(part(`${period(names)} ${year}. `));
    reference.push(part(`${period(f.documentTitle)} In `), part(f.venue, true), part(period("")));
  } else if (f.isChapter) {
    const chapter = loc.generic ? f.documentTitle : loc.label;
    if (names) reference.push(part(`${period(names)} ${year}. `), part(`${period(chapter)} In `));
    else reference.push(part(`${period(chapter)} ${year}. In `));
    reference.push(part(f.documentTitle, true), part(period("")));
  } else if (names) {
    reference.push(part(`${period(names)} ${year}. `), part(`${period(f.documentTitle)} `));
    if (f.venue) reference.push(part(f.venue, true), part(period("")));
  } else {
    reference.push(part(f.documentTitle, true), part(` ${year}.`));
    if (f.venue) reference.push(part(` ${f.venue}`, true), part(period("")));
  }
  if (f.doi) reference.push(part(` ${doiUrl(f.doi)}`));

  const who = shortName(f.authors, f.documentTitle, f.gaps);
  return {
    reference,
    inText: [part(`(${who}, ${f.year}, ${where(loc)})`)],
    footnote: null,
  };
}

function mla(f, loc) {
  const names = mlaAuthors(f.authors) ?? (f.gaps.includes("authors") ? `${PLACEHOLDER.authors}.` : null);
  const reference = [];
  const item = f.isChapter && !loc.generic ? loc.label : f.documentTitle;

  if (names) reference.push(part(`${names} `));
  if (f.isChapter) {
    reference.push(part(`${quoted(period(item))} `), part(f.documentTitle, true));
  } else {
    reference.push(part(`${quoted(period(item))} `));
    if (f.venue) reference.push(part(f.venue, true));
  }
  reference.push(part(`, ${f.year}`));
  reference.push(part(f.doi ? `, ${doiUrl(f.doi).replace(/^https?:\/\//, "")}.` : "."));

  const who = shortName(f.authors, item, f.gaps);
  const spot = loc.number != null ? `sec. ${loc.number}` : loc.generic ? loc.label : quoted(loc.label);
  return { reference, inText: [part(`(${who}, ${spot})`)], footnote: null };
}

function chicago(f, loc) {
  const item = f.isChapter && !loc.generic ? loc.label : f.documentTitle;

  const placeholder = f.gaps.includes("authors") ? PLACEHOLDER.authors : null;
  const bibNames = chicagoBibAuthors(f.authors) ?? (placeholder && `${placeholder}.`);
  const reference = [];
  if (bibNames) reference.push(part(`${bibNames} `));
  reference.push(part(`${quoted(period(item))} `));
  if (f.isChapter || f.inProceedings) {
    reference.push(part("In "), part(f.inProceedings ? f.venue : f.documentTitle, true), part(period("")));
  } else if (f.venue) reference.push(part(f.venue, true), part(period("")));
  reference.push(part(` ${f.year}.`));
  if (f.doi) reference.push(part(` ${doiUrl(f.doi)}.`));

  const noteNames = chicagoNoteAuthors(f.authors) ?? placeholder;
  const note = [];
  if (noteNames) note.push(part(`${noteNames}, `));
  note.push(part(`${quoted(period(item))} `));
  if (f.isChapter) note.push(part("in "), part(f.documentTitle, true));
  else if (f.inProceedings) note.push(part("in "), part(f.venue, true));
  else if (f.venue) note.push(part(f.venue, true));
  const paren = ` (${f.year})`;
  const tail = loc.number != null ? `, sec. ${loc.number}.` : `, ${quoted(period(loc.label))}`;
  note.push(part(`${paren}${tail}`));
  if (f.doi) note.push(part(` ${doiUrl(f.doi)}.`));

  return { reference, inText: null, footnote: note };
}

/**
 * A citation for one passage of a research document.
 *
 * `locator` is the section the passage sits in: {title, kind, index}. Drop-in
 * compatible with CiteControl, which passes a highlight-shaped object.
 */
export function researchCitation(style, doc, locator) {
  const f = facts(doc);
  const loc = sectionLocator(locator || {});
  if (style === "mla") return mla(f, loc);
  if (style === "chicago") return chicago(f, loc);
  return apa(f, loc);
}
