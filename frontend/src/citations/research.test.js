import { describe, expect, it } from "vitest";
import { toPlain } from "./format";
import {
  isConference,
  missingForCitation,
  parseAuthorList,
  researchCitation,
  sectionLocator,
} from "./research";

const PAPER = {
  title: "Attention Scaffolding for Sustained Long-Form Reading",
  authors: "A. Reader, B. Writer, and C. Editor",
  doc_kind: "paper",
  year: 2021,
  venue: "IEEE Transactions on Learning Technologies",
  doi: "10.1109/TLT.2021.1234567",
};

const TEXTBOOK = {
  title: "A Textbook of Reading and Attention",
  authors: "D. Lecturer",
  doc_kind: "textbook",
  year: 2019,
  venue: "",
  doi: "",
};

const METHOD = { title: "III. METHOD", kind: "body", index: 4 };
const CHAPTER_ONE = { title: "Chapter 1. Foundations of Attention", kind: "body", index: 0 };
const ABSTRACT = { title: "Abstract", kind: "abstract", index: 1 };

const plain = (style, doc, loc, which = "reference") => {
  const c = researchCitation(style, doc, loc);
  return toPlain(c[which] || c.footnote || c.inText);
};

describe("author lists", () => {
  it("reads a printed byline as given-name-first", () => {
    expect(parseAuthorList("A. Reader, B. Writer, and C. Editor")).toEqual([
      { last: "Reader", given: "A.", single: false },
      { last: "Writer", given: "B.", single: false },
      { last: "Editor", given: "C.", single: false },
    ]);
  });

  it("reads a semicolon-separated list as surname-first", () => {
    expect(parseAuthorList("Reader, Alice; Writer, Bob")).toEqual([
      { last: "Reader", given: "Alice", single: false },
      { last: "Writer", given: "Bob", single: false },
    ]);
  });

  it("handles a single name and a single author", () => {
    expect(parseAuthorList("Aristotle")).toEqual([{ last: "Aristotle", given: "", single: true }]);
    expect(parseAuthorList("D. Lecturer")).toEqual([
      { last: "Lecturer", given: "D.", single: false },
    ]);
  });

  it("treats an unknown or empty field as no authors", () => {
    expect(parseAuthorList("")).toEqual([]);
    expect(parseAuthorList("Unknown")).toEqual([]);
    expect(parseAuthorList(null)).toEqual([]);
  });

  it("drops a generational suffix rather than reading it as a name", () => {
    expect(parseAuthorList("Reader, Alice; Writer, Bob, Jr.").map((n) => n.last)).toEqual([
      "Reader",
      "Writer",
    ]);
  });
});

describe("section locators", () => {
  it("takes the number from a roman or arabic heading", () => {
    expect(sectionLocator(METHOD).number).toBe(3);
    expect(sectionLocator(CHAPTER_ONE).number).toBe(1);
    expect(sectionLocator({ title: "2.3 Evaluation", kind: "body" }).number).toBe(2);
  });

  it("names the abstract and the references by kind", () => {
    expect(sectionLocator(ABSTRACT).label).toBe("Abstract");
    expect(sectionLocator({ title: "REFERENCES", kind: "references" }).label).toBe("References");
  });

  it("never invents a number for an untitled section", () => {
    const loc = sectionLocator({ title: "", kind: "body", index: 0 });
    expect(loc.number).toBeNull();
    expect(loc.label).toBe("Opening section");
    expect(loc.generic).toBe(true);
  });
});

describe("journal article", () => {
  it("formats an APA reference and in-text citation", () => {
    expect(plain("apa", PAPER, METHOD)).toBe(
      "Reader, A., Writer, B., & Editor, C. (2021). " +
        "Attention Scaffolding for Sustained Long-Form Reading. " +
        "IEEE Transactions on Learning Technologies. https://doi.org/10.1109/TLT.2021.1234567"
    );
    expect(plain("apa", PAPER, METHOD, "inText")).toBe("(Reader et al., 2021, Section 3)");
  });

  it("formats an MLA reference and in-text citation", () => {
    expect(plain("mla", PAPER, METHOD)).toBe(
      "Reader, A., et al. “Attention Scaffolding for Sustained Long-Form Reading.” " +
        "IEEE Transactions on Learning Technologies, 2021, doi.org/10.1109/TLT.2021.1234567."
    );
    expect(plain("mla", PAPER, METHOD, "inText")).toBe("(Reader et al., sec. 3)");
  });

  it("formats a Chicago note", () => {
    expect(plain("chicago", PAPER, METHOD, "footnote")).toBe(
      "A. Reader, B. Writer, and C. Editor, " +
        "“Attention Scaffolding for Sustained Long-Form Reading.” " +
        "IEEE Transactions on Learning Technologies (2021), sec. 3. " +
        "https://doi.org/10.1109/TLT.2021.1234567."
    );
  });

  it("italicises the venue, not the article title", () => {
    const c = researchCitation("apa", PAPER, METHOD);
    const italics = c.reference.filter((p) => p.italic).map((p) => p.text);
    expect(italics).toEqual(["IEEE Transactions on Learning Technologies"]);
  });
});

describe("textbook chapter", () => {
  it("cites the chapter inside the book in APA", () => {
    // APA inverts the name in a reference entry; Chicago's note form does not.
    expect(plain("apa", TEXTBOOK, CHAPTER_ONE)).toBe(
      "Lecturer, D. (2019). Chapter 1. Foundations of Attention. In A Textbook of Reading and Attention."
    );
  });

  it("cites the chapter inside the book in MLA", () => {
    expect(plain("mla", TEXTBOOK, CHAPTER_ONE)).toBe(
      "Lecturer, D. “Chapter 1. Foundations of Attention.” A Textbook of Reading and Attention, 2019."
    );
  });

  it("cites the chapter inside the book in Chicago", () => {
    expect(plain("chicago", TEXTBOOK, CHAPTER_ONE, "footnote")).toBe(
      "D. Lecturer, “Chapter 1. Foundations of Attention.” in A Textbook of Reading and Attention (2019), sec. 1."
    );
  });

  it("italicises the book title", () => {
    const c = researchCitation("mla", TEXTBOOK, CHAPTER_ONE);
    expect(c.reference.filter((p) => p.italic).map((p) => p.text)).toEqual([
      "A Textbook of Reading and Attention",
    ]);
  });
});

describe("missing metadata is never invented", () => {
  const bare = { title: "An Untitled Preprint", authors: "", doc_kind: "paper" };

  it("shows a gap as a gap, not as n.d.", () => {
    // "n.d." reads as a fact about the document. An unfilled field is not
    // that, and a citation carrying one must look unfinished so it cannot be
    // pasted into a paper unnoticed.
    expect(plain("apa", bare, METHOD)).toContain("[Year]");
    expect(plain("apa", bare, METHOD)).not.toContain("n.d.");
    expect(plain("mla", bare, METHOD)).toContain("[Year]");
    expect(plain("chicago", bare, METHOD, "footnote")).toContain("[Year]");
  });

  it("says n.d. once somebody has confirmed there is no date", () => {
    const undated = { ...bare, authors: "A. Reader", no_date: true };
    expect(plain("apa", undated, METHOD)).toContain("(n.d.)");
    expect(plain("apa", undated, METHOD)).not.toContain("[Year]");
    expect(plain("mla", undated, METHOD)).toContain(", n.d.");
    expect(plain("chicago", undated, METHOD, "footnote")).toContain("(n.d.)");
  });

  it("marks a missing author rather than falling back to the title", () => {
    expect(plain("apa", bare, METHOD, "inText")).toBe("([Author], [Year], Section 3)");
    expect(plain("apa", bare, METHOD)).toContain("[Author]");
    expect(plain("mla", bare, METHOD)).toContain("[Author]");
    expect(plain("chicago", bare, METHOD, "footnote")).toContain("[Author]");
  });

  it("marks a missing title too", () => {
    const untitled = { title: "", authors: "A. Reader", year: 2020, doc_kind: "paper" };
    expect(plain("apa", untitled, METHOD)).toContain("[Title]");
  });

  it("names the fields a citation cannot be written without", () => {
    expect(missingForCitation(bare).sort()).toEqual(["authors", "year"]);
    expect(missingForCitation(PAPER)).toEqual([]);
    expect(missingForCitation({ ...bare, authors: "Unknown" })).toContain("authors");
    expect(missingForCitation({ ...bare, authors: "A. Reader", no_date: true })).toEqual([]);
  });

  it("counts a guessed field as needing review", () => {
    const guessed = { ...PAPER, unverified: ["year"] };
    expect(missingForCitation(guessed)).toEqual(["year"]);
  });

  it("leaves out a venue and a DOI it does not have", () => {
    const text = plain("apa", bare, METHOD);
    expect(text).not.toContain("doi.org");
    expect(text).not.toContain("undefined");
    expect(text).not.toContain("null");
  });

  it("never emits the word undefined for any style or document", () => {
    for (const style of ["apa", "mla", "chicago"]) {
      for (const doc of [PAPER, TEXTBOOK, bare]) {
        for (const loc of [METHOD, CHAPTER_ONE, ABSTRACT, {}]) {
          const c = researchCitation(style, doc, loc);
          const all = [c.reference, c.inText, c.footnote].filter(Boolean).map(toPlain).join(" ");
          expect(all).not.toMatch(/undefined|null|NaN/);
        }
      }
    }
  });
});

describe("conference papers", () => {
  const CONFERENCE = {
    title: "Detecting Intrusions with Honeypots",
    authors: "A. Reader, B. Writer",
    doc_kind: "paper",
    year: 2022,
    venue: "Proceedings of the 31st USENIX Security Symposium",
    doi: "10.1145/1234.5678",
  };

  it("is recognised from the venue", () => {
    expect(isConference("Proceedings of the 31st USENIX Security Symposium")).toBe(true);
    expect(isConference("Proc. 4th Int. Conf. Persuasive Technol.")).toBe(true);
    expect(isConference("IEEE Transactions on Learning Technologies")).toBe(false);
    expect(isConference("")).toBe(false);
  });

  it("is cited inside its proceedings in APA", () => {
    expect(plain("apa", CONFERENCE, METHOD)).toBe(
      "Reader, A., & Writer, B. (2022). Detecting Intrusions with Honeypots. " +
        "In Proceedings of the 31st USENIX Security Symposium. https://doi.org/10.1145/1234.5678"
    );
  });

  it("is cited inside its proceedings in Chicago", () => {
    expect(plain("chicago", CONFERENCE, METHOD, "footnote")).toContain(
      "in Proceedings of the 31st USENIX Security Symposium"
    );
  });

  it("still italicises the venue and not the paper title", () => {
    const c = researchCitation("apa", CONFERENCE, METHOD);
    expect(c.reference.filter((p) => p.italic).map((p) => p.text)).toEqual([
      "Proceedings of the 31st USENIX Security Symposium",
    ]);
  });

  it("leaves a journal article as it was", () => {
    expect(plain("apa", PAPER, METHOD)).toContain(
      "IEEE Transactions on Learning Technologies. https://doi.org/"
    );
    expect(plain("apa", PAPER, METHOD)).not.toContain(" In ");
  });
});
