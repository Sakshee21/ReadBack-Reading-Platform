import { describe, it, expect } from "vitest";
import { buildNotesMarkdown, notesFileName } from "./exportMarkdown";

const h = (over) => ({
  id: 1,
  chapter_index: 1,
  chapter_title: "Down the Rabbit-Hole",
  session_index: 2,
  session_number: 4,
  start: 0,
  quote: "Alice was beginning",
  color: "yellow",
  comment: null,
  created_at: "2026-10-18T10:00:00",
  ...over,
});

describe("notes export", () => {
  it("markdown_export_groups_by_chapter_in_order_with_quote_colour_location_and_comment", () => {
    const md = buildNotesMarkdown({
      bookTitle: "Alice",
      highlights: [
        h({ id: 3, chapter_index: 2, chapter_title: "The Pool", session_number: 9, quote: "pool quote", color: "blue", comment: "key moment" }),
        h({ id: 1 }),
        h({ id: 2, start: 50, quote: "later in one", color: "green" }),
      ],
    });
    expect(md.startsWith("# Alice")).toBe(true);
    const ch1 = md.indexOf("## Down the Rabbit-Hole");
    const ch2 = md.indexOf("## The Pool");
    expect(ch1).toBeGreaterThan(0);
    expect(ch2).toBeGreaterThan(ch1);
    expect(md.indexOf("> Alice was beginning")).toBeLessThan(md.indexOf("> later in one"));
    expect(md.indexOf("> later in one")).toBeLessThan(ch2);
    expect(md).toContain("Blue");
    expect(md).toContain("Blue · Session 9");
    expect(md).toContain("Yellow · Session 4");
    expect(md).toContain("key moment");
  });

  it("markdown_export_handles_no_comment_and_multiline_quotes", () => {
    const md = buildNotesMarkdown({
      bookTitle: "T",
      highlights: [h({ quote: "line one\n\nline two", comment: null })],
    });
    expect(md).toContain("> line one\n> \n> line two");
    expect(md).not.toMatch(/Comment:/);
  });

  it("untitled_chapter_and_missing_session_number_fall_back", () => {
    const md = buildNotesMarkdown({
      bookTitle: "T",
      highlights: [h({ chapter_title: "", chapter_index: 3, session_number: null })],
    });
    expect(md).toContain("## Chapter 3");
    expect(md).toContain("Yellow\n");
    expect(md).not.toMatch(/Session/);
  });

  it("comment_lines_cannot_change_the_document_structure", () => {
    const md = buildNotesMarkdown({
      bookTitle: "T",
      highlights: [h({ comment: "# not a heading\n> not a quote\n- not a list\n1. not numbered\nplain" })],
    });
    expect(md).toContain("\\# not a heading");
    expect(md).toContain("\\> not a quote");
    expect(md).toContain("\\- not a list");
    expect(md).toContain("1\\. not numbered");
    expect(md).toContain("\nplain");
    expect(md).not.toMatch(/^# not a heading/m);
  });

  it("carriage_returns_are_removed_from_quotes_and_comments", () => {
    const md = buildNotesMarkdown({
      bookTitle: "T",
      highlights: [h({ quote: "one\r\ntwo", comment: "a\r\nb" })],
    });
    expect(md).not.toContain("\r");
    expect(md).toContain("> one\n> two");
  });

  it("empty_list_still_has_the_title", () => {
    expect(buildNotesMarkdown({ bookTitle: "Alice", highlights: [] })).toContain("# Alice");
  });

  it("notes_file_name_is_safe", () => {
    expect(notesFileName("Alice's Adventures")).toBe("Alice's Adventures - notes.md");
    expect(notesFileName('A/B\\C:D*E?"F<G>H|')).toBe("A B C D E F G H - notes.md");
    expect(notesFileName("   ")).toBe("Book - notes.md");
    expect(notesFileName(undefined)).toBe("Book - notes.md");
  });
});
