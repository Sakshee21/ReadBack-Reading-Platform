import { describe, it, expect } from "vitest";
import { buildNotesCsv, notesCsvFileName } from "./exportCsv";

const book = {
  title: "Alice's Adventures in Wonderland",
  author: "Carroll, Lewis",
  published_year: 1865,
  gutenberg_id: 11,
  is_user_uploaded: false,
};

const h = (over) => ({
  id: 1,
  chapter_index: 1,
  chapter_title: "Chapter 1",
  session_index: 2,
  session_number: 4,
  start: 0,
  quote: "Alice was beginning",
  color: "yellow",
  comment: null,
  themes: [],
  created_at: "2026-10-18T10:00:00",
  ...over,
});

const rows = (csv) => csv.split("\r\n").filter(Boolean);

describe("notes CSV", () => {
  it("has_a_header_and_one_quoted_row_per_note_with_crlf_line_ends", () => {
    const csv = buildNotesCsv({ book, style: "apa", highlights: [h({ comment: "key", themes: [{ theme: "romance", label: "Romance & courtship" }, { theme: "war_conflict", label: "War & conflict" }] })] });
    const lines = rows(csv);
    expect(lines[0]).toBe("book,author,chapter,chapter_title,quote,comment,colour,themes,citation,created");
    expect(lines).toHaveLength(2);
    expect(lines[1]).toBe(
      '"Alice\'s Adventures in Wonderland","Carroll, Lewis","Chapter 1","Chapter 1","Alice was beginning","key","Yellow","Romance & courtship; War & conflict","(Carroll, 1865, Chapter 1)","2026-10-18T10:00:00"'
    );
    expect(csv.endsWith("\r\n")).toBe(true);
  });

  it("orders_notes_by_chapter_then_passage_then_position", () => {
    const csv = buildNotesCsv({
      book,
      style: "apa",
      highlights: [
        h({ id: 3, chapter_index: 2, chapter_title: "The Pool", quote: "third" }),
        h({ id: 2, start: 50, quote: "second" }),
        h({ id: 1, quote: "first" }),
      ],
    });
    expect(rows(csv).slice(1).map((l) => l.split('","')[4])).toEqual(["first", "second", "third"]);
  });

  it("doubles_quotes_and_keeps_newlines_inside_the_cell", () => {
    const csv = buildNotesCsv({ book, style: "apa", highlights: [h({ quote: 'She said "hello"\nthen left', comment: 'a "note"' })] });
    expect(csv).toContain('"She said ""hello""\nthen left"');
    expect(csv).toContain('"a ""note"""');
  });

  it.each(["=cmd|' /C calc'!A0", "+1+1", "-2", "@SUM(A1)", "\tindented", "\rcarriage"])(
    "a_cell_beginning_with_a_formula_character_is_neutralised_%#",
    (evil) => {
      const csv = buildNotesCsv({ book, style: "apa", highlights: [h({ quote: evil, comment: evil })] });
      const cells = csv.split("\r\n")[1];
      expect(cells).not.toContain(`"${evil.slice(0, 1)}`.replace('""', '"'));
      expect(cells).toContain(`"'${evil.replace(/"/g, '""')}"`);
    }
  );

  it("a_leading_space_before_a_formula_does_not_get_past_the_guard", () => {
    const csv = buildNotesCsv({ book, style: "apa", highlights: [h({ quote: "  =1+1", comment: " @SUM(A1)" })] });
    expect(csv).toContain('"\'  =1+1"');
    expect(csv).toContain('"\' @SUM(A1)"');
  });

  it("the_title_and_author_columns_are_guarded_too", () => {
    const evil = { ...book, title: "=HYPERLINK(\"http://x\")", author: "+evil, Mal" };
    const csv = buildNotesCsv({ book: evil, style: "apa", highlights: [h()] });
    const line = csv.split("\r\n")[1];
    expect(line.startsWith('"\'=HYPERLINK(""http://x"")","\'+evil, Mal"')).toBe(true);
  });

  it("an_untitled_lead_in_chapter_is_labelled_opening_section", () => {
    const line = buildNotesCsv({ book, style: "apa", highlights: [h({ chapter_title: "", chapter_index: 0 })] }).split("\r\n")[1];
    expect(line).toContain('"Opening section"');
    expect(line).not.toContain("Chapter 1");
  });

  it("the_citation_column_follows_the_style", () => {
    expect(rows(buildNotesCsv({ book, style: "mla", highlights: [h()] }))[1]).toContain('"(Carroll, ch. 1)"');
    expect(rows(buildNotesCsv({ book, style: "chicago", highlights: [h()] }))[1]).toContain(
      '"Lewis Carroll, Alice\'s Adventures in Wonderland (1865; Project Gutenberg), chap. 1."'
    );
  });

  it("an_empty_set_is_just_the_header", () => {
    expect(rows(buildNotesCsv({ book, style: "apa", highlights: [] }))).toHaveLength(1);
  });

  it("file_name_is_safe", () => {
    expect(notesCsvFileName("Alice: a/b?")).toBe("Alice a b - notes.csv");
    expect(notesCsvFileName("")).toBe("Book - notes.csv");
  });
});
