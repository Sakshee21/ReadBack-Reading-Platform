import { describe, it, expect } from "vitest";
import {
  STYLES,
  parseAuthor,
  chapterLocator,
  citation,
  toPlain,
  toHtml,
  toMarkdown,
} from "./format";

const shelley = {
  title: "Frankenstein; or, the modern prometheus",
  author: "Shelley, Mary Wollstonecraft",
  published_year: 1818,
  gutenberg_id: 84,
  is_user_uploaded: false,
};
const ch5 = { chapter_title: "Chapter 5", chapter_index: 5 };

const plain = (style, book, h) => {
  const c = citation(style, book, h);
  return {
    reference: toPlain(c.reference),
    inText: c.inText && toPlain(c.inText),
    footnote: c.footnote && toPlain(c.footnote),
  };
};

describe("styles", () => {
  it("offers_apa_mla_and_chicago", () => {
    expect(STYLES).toEqual(["apa", "mla", "chicago"]);
  });
});

describe("parseAuthor", () => {
  it("splits_last_comma_given", () => {
    expect(parseAuthor("Shelley, Mary Wollstonecraft")).toMatchObject({ last: "Shelley", given: "Mary Wollstonecraft", single: false });
  });
  it("a_single_name_is_used_whole", () => {
    expect(parseAuthor("Voltaire")).toMatchObject({ last: "Voltaire", given: "", single: true });
  });
  it("blank_and_unknown_authors_are_unknown", () => {
    for (const name of ["", "  ", "Unknown", "unknown", null, undefined]) expect(parseAuthor(name).unknown).toBe(true);
  });
});

describe("chapterLocator", () => {
  it("reads_numbers_and_roman_numerals", () => {
    expect(chapterLocator({ chapter_title: "Chapter 5", chapter_index: 5 })).toEqual({ number: 5, label: "Chapter 5", generic: false });
    expect(chapterLocator({ chapter_title: "CHAPTER XIV", chapter_index: 14 })).toEqual({ number: 14, label: "Chapter 14", generic: false });
    expect(chapterLocator({ chapter_title: "chapter I.", chapter_index: 1 })).toEqual({ number: 1, label: "Chapter 1", generic: false });
  });
  it("other_titles_are_used_as_they_are", () => {
    expect(chapterLocator({ chapter_title: "The Ball", chapter_index: 3 })).toEqual({ number: null, label: "The Ball", generic: false });
    expect(chapterLocator({ chapter_title: "Chapter One", chapter_index: 1 })).toEqual({ number: null, label: "Chapter One", generic: false });
  });
  it("a_title_that_starts_with_the_chapter_number_keeps_the_number", () => {
    for (const title of ["CHAPTER I. THE RABBIT-HOLE", "Chapter 1: Down the Rabbit-Hole", "Chapter I - Down", "CHAPTER I.\nDown the Rabbit-Hole"]) {
      expect(chapterLocator({ chapter_title: title, chapter_index: 9 })).toEqual({ number: 1, label: "Chapter 1", generic: false });
    }
  });
  it("words_made_of_roman_letters_are_not_numerals", () => {
    for (const title of ["Chapter Civil", "Chapter Mix", "Chapter Livid", "Chapter Mixed Feelings"]) {
      expect(chapterLocator({ chapter_title: title, chapter_index: 2 }).number).toBeNull();
    }
    expect(chapterLocator({ chapter_title: "CHAPTER XLIV", chapter_index: 2 }).number).toBe(44);
  });
  it("an_untitled_chapter_is_never_given_a_number_it_may_not_have", () => {
    expect(chapterLocator({ chapter_title: "", chapter_index: 0 })).toEqual({ number: null, label: "Opening section", generic: true });
    expect(chapterLocator({ chapter_title: null, chapter_index: 4 })).toEqual({ number: null, label: "Section 5", generic: true });
  });
});

describe("APA", () => {
  it("formats_a_gutenberg_book", () => {
    expect(plain("apa", shelley, ch5)).toEqual({
      reference: "Shelley, M. W. (1818). Frankenstein; or, the modern prometheus. Project Gutenberg. https://www.gutenberg.org/ebooks/84",
      inText: "(Shelley, 1818, Chapter 5)",
      footnote: null,
    });
  });
  it("uses_nd_when_there_is_no_year", () => {
    const c = plain("apa", { ...shelley, published_year: null }, ch5);
    expect(c.reference).toContain("(n.d.)");
    expect(c.inText).toBe("(Shelley, n.d., Chapter 5)");
  });
  it("marks_an_uploaded_file", () => {
    const book = { title: "My Thesis Notes", author: "Doe, Jane", published_year: null, gutenberg_id: null, is_user_uploaded: true };
    expect(plain("apa", book, { chapter_title: "", chapter_index: 1 })).toEqual({
      reference: "Doe, J. (n.d.). My Thesis Notes [Uploaded file].",
      inText: "(Doe, n.d., Section 2)",
      footnote: null,
    });
  });
  it("a_single_name_author", () => {
    const book = { title: "Candide", author: "Voltaire", published_year: 1759, gutenberg_id: 19942, is_user_uploaded: false };
    const c = plain("apa", book, { chapter_title: "Chapter 3", chapter_index: 3 });
    expect(c.reference).toBe("Voltaire. (1759). Candide. Project Gutenberg. https://www.gutenberg.org/ebooks/19942");
    expect(c.inText).toBe("(Voltaire, 1759, Chapter 3)");
  });
  it("an_unknown_author_moves_the_title_first", () => {
    const book = { title: "A Tale of Two: Cities", author: "Unknown", published_year: 1900, gutenberg_id: 5, is_user_uploaded: false };
    const c = plain("apa", book, ch5);
    expect(c.reference).toBe("A Tale of Two: Cities. (1900). Project Gutenberg. https://www.gutenberg.org/ebooks/5");
    expect(c.inText).toBe("(“A Tale of Two”, 1900, Chapter 5)");
  });
  it("a_verbatim_chapter_title_is_quoted", () => {
    const book = { ...shelley, author: "Austen, Jane", title: "Pride and Prejudice", published_year: 1813 };
    expect(plain("apa", book, { chapter_title: "The Ball", chapter_index: 3 }).inText).toBe("(Austen, 1813, “The Ball”)");
  });
});

describe("MLA", () => {
  it("formats_a_gutenberg_book", () => {
    expect(plain("mla", shelley, ch5)).toEqual({
      reference: "Shelley, Mary Wollstonecraft. Frankenstein; or, the modern prometheus. 1818. Project Gutenberg, www.gutenberg.org/ebooks/84.",
      inText: "(Shelley, ch. 5)",
      footnote: null,
    });
  });
  it("leaves_out_an_unknown_year", () => {
    expect(plain("mla", { ...shelley, published_year: null }, ch5).reference).toBe(
      "Shelley, Mary Wollstonecraft. Frankenstein; or, the modern prometheus. Project Gutenberg, www.gutenberg.org/ebooks/84."
    );
  });
  it("an_uploaded_file_has_no_url", () => {
    const book = { title: "My Thesis Notes", author: "Doe, Jane", published_year: null, gutenberg_id: null, is_user_uploaded: true };
    const c = plain("mla", book, { chapter_title: "", chapter_index: 1 });
    expect(c.reference).toBe("Doe, Jane. My Thesis Notes. Uploaded file.");
    expect(c.inText).toBe("(Doe, Section 2)");
  });
  it("single_unknown_and_verbatim_cases", () => {
    const candide = { title: "Candide", author: "Voltaire", published_year: 1759, gutenberg_id: 19942, is_user_uploaded: false };
    expect(plain("mla", candide, ch5).reference).toBe("Voltaire. Candide. 1759. Project Gutenberg, www.gutenberg.org/ebooks/19942.");
    const anon = { title: "A Tale of Two: Cities", author: "", published_year: 1900, gutenberg_id: 5, is_user_uploaded: false };
    expect(plain("mla", anon, ch5).inText).toBe("(“A Tale of Two”, ch. 5)");
    expect(plain("mla", { ...shelley, author: "Austen, Jane" }, { chapter_title: "The Ball", chapter_index: 3 }).inText).toBe("(Austen, “The Ball”)");
  });
});

describe("Chicago", () => {
  it("formats_a_gutenberg_book_with_a_footnote_and_no_in_text_form", () => {
    expect(plain("chicago", shelley, ch5)).toEqual({
      reference: "Shelley, Mary Wollstonecraft. Frankenstein; or, the modern prometheus. 1818. Project Gutenberg. https://www.gutenberg.org/ebooks/84.",
      inText: null,
      footnote: "Mary Wollstonecraft Shelley, Frankenstein; or, the modern prometheus (1818; Project Gutenberg), chap. 5.",
    });
  });
  it("covers_uploads_single_names_unknown_authors_and_verbatim_chapters", () => {
    const upload = { title: "My Thesis Notes", author: "Doe, Jane", published_year: null, gutenberg_id: null, is_user_uploaded: true };
    const u = plain("chicago", upload, { chapter_title: "", chapter_index: 1 });
    expect(u.reference).toBe("Doe, Jane. My Thesis Notes. Uploaded file.");
    expect(u.footnote).toBe("Jane Doe, My Thesis Notes (uploaded file), section 2.");
    const candide = { title: "Candide", author: "Voltaire", published_year: 1759, gutenberg_id: 19942, is_user_uploaded: false };
    expect(plain("chicago", candide, { chapter_title: "Chapter 3", chapter_index: 3 }).footnote).toBe(
      "Voltaire, Candide (1759; Project Gutenberg), chap. 3."
    );
    const anon = { title: "A Tale of Two", author: "Unknown", published_year: 1900, gutenberg_id: 5, is_user_uploaded: false };
    expect(plain("chicago", anon, ch5).footnote).toBe("A Tale of Two (1900; Project Gutenberg), chap. 5.");
    expect(plain("chicago", { ...shelley, author: "Austen, Jane", title: "Pride and Prejudice", published_year: 1813 }, { chapter_title: "The Ball", chapter_index: 3 }).footnote).toBe(
      "Jane Austen, Pride and Prejudice (1813; Project Gutenberg), “The Ball.”"
    );
  });
});

describe("untitled lead-in chapters", () => {
  it("are_cited_by_a_plain_label_never_as_chapter_1", () => {
    const lead = { chapter_title: "", chapter_index: 0 };
    expect(plain("apa", shelley, lead).inText).toBe("(Shelley, 1818, Opening section)");
    expect(plain("mla", shelley, lead).inText).toBe("(Shelley, Opening section)");
    expect(plain("chicago", shelley, lead).footnote).toBe(
      "Mary Wollstonecraft Shelley, Frankenstein; or, the modern prometheus (1818; Project Gutenberg), opening section."
    );
    expect(plain("mla", shelley, lead).inText).not.toBe(plain("mla", shelley, { chapter_title: "Chapter 1", chapter_index: 1 }).inText);
  });
});

describe("chicago footnote punctuation", () => {
  it("does_not_double_a_full_stop_that_ends_the_chapter_title", () => {
    const note = plain("chicago", { ...shelley, author: "Carroll, Lewis", title: "Alice" }, { chapter_title: "Down the Rabbit-Hole.", chapter_index: 1 }).footnote;
    expect(note.endsWith("\u201CDown the Rabbit-Hole.\u201D")).toBe(true);
    expect(note).not.toContain("..");
  });
});

describe("authors typed without a comma", () => {
  it("the_last_word_is_the_surname_when_there_are_several_words", () => {
    expect(parseAuthor("Jane Doe")).toMatchObject({ last: "Doe", given: "Jane", single: false });
    expect(parseAuthor("Mary Wollstonecraft Shelley")).toMatchObject({ last: "Shelley", given: "Mary Wollstonecraft", single: false });
  });
  it("an_upload_by_first_last_is_cited_with_initials", () => {
    const book = { title: "Notes", author: "Jane Doe", published_year: null, gutenberg_id: null, is_user_uploaded: true };
    expect(plain("apa", book, ch5).reference).toBe("Doe, J. (n.d.). Notes [Uploaded file].");
    expect(plain("apa", book, ch5).inText).toBe("(Doe, n.d., Chapter 5)");
  });
});

describe("initials", () => {
  it("handles_several_given_names_and_hyphens", () => {
    const apa = (author) => plain("apa", { ...shelley, author }, ch5).reference.split(" (")[0];
    expect(apa("Gilman, Charlotte Perkins")).toBe("Gilman, C. P.");
    expect(apa("Sartre, Jean-Paul")).toBe("Sartre, J.-P.");
    expect(apa("Carroll, Lewis")).toBe("Carroll, L.");
  });
});

describe("renderers", () => {
  const c = citation("apa", shelley, ch5);
  it("only_the_title_is_italic", () => {
    expect(toMarkdown(c.reference)).toBe(
      "Shelley, M. W. (1818). *Frankenstein; or, the modern prometheus*. Project Gutenberg. https://www.gutenberg.org/ebooks/84"
    );
    expect(toHtml(c.reference)).toContain("<i>Frankenstein; or, the modern prometheus</i>");
  });
  it("html_is_escaped", () => {
    const evil = citation("apa", { ...shelley, title: "<script>alert(1)</script> & co" }, ch5);
    const html = toHtml(evil.reference);
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
    expect(html).toContain("&amp; co");
  });
  it("a_title_that_ends_in_a_question_mark_gets_no_second_full_stop", () => {
    const q = citation("apa", { ...shelley, title: "Who Goes There?" }, ch5);
    expect(toPlain(q.reference)).toContain("Who Goes There? Project Gutenberg");
  });
});

describe("author name edge cases", () => {
  const apa = (author) => plain("apa", { ...shelley, author }, ch5);

  it("a_suffix_is_not_taken_for_a_given_name", () => {
    expect(apa("Doe, Jane, Jr.").reference.split(" (")[0]).toBe("Doe, J.");
    expect(parseAuthor("Doe, Jane, Jr.")).toMatchObject({ last: "Doe", given: "Jane" });
  });

  it("a_parenthesised_real_name_is_dropped", () => {
    expect(parseAuthor("Twain, Mark (Samuel Clemens)")).toMatchObject({ last: "Twain", given: "Mark" });
  });

  it("a_comma_with_no_given_name_is_a_single_name", () => {
    expect(parseAuthor("Voltaire,")).toMatchObject({ last: "Voltaire", given: "", single: true });
    expect(apa("Voltaire,").inText).toBe("(Voltaire, 1818, Chapter 5)");
  });

  it("anonymous_is_the_author_in_apa", () => {
    expect(parseAuthor("Anonymous")).toMatchObject({ unknown: false, last: "Anonymous", single: true });
    expect(apa("Anonymous").inText).toBe("(Anonymous, 1818, Chapter 5)");
  });

  it("unknown_or_empty_still_means_no_author", () => {
    for (const name of ["", "Unknown", null]) expect(parseAuthor(name).unknown).toBe(true);
  });
});
