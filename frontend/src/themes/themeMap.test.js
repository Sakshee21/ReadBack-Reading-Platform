import { describe, expect, it } from "vitest";
import {
  MIN_LABEL_COLUMNS,
  READ_SO_FAR,
  WHOLE_BOOK,
  cellsByChapter,
  cellsInRange,
  chapterTitle,
  chaptersInRange,
  columnCount,
  shortChapterLabel,
  thinChapterLabels,
} from "./themeMap";

const chapter = (index, start, end, title = "") => ({ index, start, end, title });

describe("how wide the chart is", () => {
  it("fits the part the reader has reached by default", () => {
    // The complaint this fixes: 20 passages read of 500 drew a chart that was
    // 96% empty.
    expect(columnCount({ total: 500, reached: 20, scale: READ_SO_FAR })).toBe(20);
  });

  it("spans the whole book when asked", () => {
    expect(columnCount({ total: 500, reached: 20, scale: WHOLE_BOOK })).toBe(500);
  });

  it("is the whole book once the reader has finished", () => {
    expect(columnCount({ total: 40, reached: 40, scale: READ_SO_FAR })).toBe(40);
  });

  it("never runs past the end of the book", () => {
    expect(columnCount({ total: 10, reached: 99, scale: READ_SO_FAR })).toBe(10);
  });

  it("falls back to the whole book rather than collapsing to nothing", () => {
    // An older server with no `reached` field, or a reader who has somehow
    // reached zero passages.
    expect(columnCount({ total: 30, scale: READ_SO_FAR })).toBe(30);
    expect(columnCount({ total: 30, reached: 0, scale: READ_SO_FAR })).toBe(30);
  });

  it("is never zero, so the grid always has a column", () => {
    expect(columnCount({ total: 0, reached: 0 })).toBe(1);
    expect(columnCount({})).toBe(1);
  });
});

describe("chapters within the drawn range", () => {
  const chapters = [chapter(0, 0, 4), chapter(1, 5, 9), chapter(2, 10, 14)];

  it("keeps only the chapters the range touches", () => {
    expect(chaptersInRange(chapters, 7).map((c) => c.index)).toEqual([0, 1]);
  });

  it("clips the last chapter to the end of the range", () => {
    expect(chaptersInRange(chapters, 7).at(-1)).toMatchObject({ index: 1, start: 5, end: 6 });
  });

  it("keeps them all when the range is the whole book", () => {
    expect(chaptersInRange(chapters, 15)).toHaveLength(3);
  });
});

describe("thinning the chapter labels", () => {
  it("labels every chapter when they are far apart", () => {
    const chapters = [chapter(0, 0, 9), chapter(1, 10, 19), chapter(2, 20, 29)];
    expect(thinChapterLabels(chapters).map((c) => c.index)).toEqual([0, 1, 2]);
  });

  it("drops labels that would collide in a long book", () => {
    // 40 chapters of two passages each: labelling all of them is what produced
    // the unreadable "C|C|C".
    const chapters = Array.from({ length: 40 }, (_, i) => chapter(i, i * 2, i * 2 + 1));
    const labelled = thinChapterLabels(chapters);
    expect(labelled.length).toBeLessThan(chapters.length);
    for (let i = 1; i < labelled.length; i += 1) {
      expect(labelled[i].start - labelled[i - 1].start).toBeGreaterThanOrEqual(MIN_LABEL_COLUMNS);
    }
  });

  it("always labels the first chapter, so the chart has an anchor", () => {
    const chapters = Array.from({ length: 10 }, (_, i) => chapter(i, i, i));
    expect(thinChapterLabels(chapters)[0].index).toBe(0);
  });

  it("takes a wider spacing when asked", () => {
    const chapters = Array.from({ length: 20 }, (_, i) => chapter(i, i * 3, i * 3 + 2));
    expect(thinChapterLabels(chapters, { minColumns: 30 }).length).toBeLessThan(
      thinChapterLabels(chapters, { minColumns: 5 }).length
    );
  });

  it("copes with no chapters at all", () => {
    expect(thinChapterLabels([])).toEqual([]);
    expect(thinChapterLabels()).toEqual([]);
  });
});

describe("short chapter labels", () => {
  it("uses the printed number when the title has one", () => {
    expect(shortChapterLabel(chapter(0, 0, 3, "CHAPTER IV. THE BALL"), 1)).toBe("Ch 4");
    expect(shortChapterLabel(chapter(7, 0, 3, "Chapter 12"), 3)).toBe("Ch 12");
  });

  it("falls back to the position in the book when it has none", () => {
    expect(shortChapterLabel(chapter(0, 0, 3, "The Ball"), 2)).toBe("Ch 2");
    expect(shortChapterLabel(chapter(0, 0, 3, ""), 5)).toBe("Ch 5");
  });

  it("keeps the full title for the tooltip", () => {
    expect(chapterTitle(chapter(0, 0, 3, "CHAPTER IV. THE BALL"))).toBe("CHAPTER IV. THE BALL");
    expect(chapterTitle(chapter(0, 0, 3, ""))).toBe("Opening section");
  });
});

describe("collapsing a row into chapters", () => {
  const chapters = [chapter(0, 0, 3, "One"), chapter(1, 4, 7, "Two"), chapter(2, 8, 11, "Three")];
  const cells = [
    { pos: 0, micro_session_id: 10, score: 3 },
    { pos: 2, micro_session_id: 12, score: 5 },
    { pos: 3, micro_session_id: 13, score: 4 },
    { pos: 9, micro_session_id: 19, score: 3 },
  ];

  it("gives one cell per chapter, at its strongest score", () => {
    const out = cellsByChapter(cells, chapters);
    expect(out.map((c) => [c.chapter.index, c.score])).toEqual([
      [0, 5],
      [2, 3],
    ]);
  });

  it("counts the passages behind each chapter cell", () => {
    expect(cellsByChapter(cells, chapters)[0].count).toBe(3);
  });

  it("links to the strongest passage, which is the one worth opening", () => {
    expect(cellsByChapter(cells, chapters)[0].micro_session_id).toBe(12);
  });

  it("leaves out chapters with no tag at all", () => {
    expect(cellsByChapter(cells, chapters).map((c) => c.chapter.index)).not.toContain(1);
  });

  it("cannot invent a cell for a chapter the reader has not reached", () => {
    // Unreached chapters carry no cells, because the server sent none.
    const reachedOnly = cells.filter((c) => c.pos <= 3);
    expect(cellsByChapter(reachedOnly, chapters).map((c) => c.chapter.index)).toEqual([0]);
  });

  it("stays in book order", () => {
    const shuffled = [...cells].reverse();
    expect(cellsByChapter(shuffled, chapters).map((c) => c.chapter.index)).toEqual([0, 2]);
  });

  it("ignores a cell that belongs to no chapter in range", () => {
    expect(cellsByChapter([{ pos: 99, micro_session_id: 1, score: 5 }], chapters)).toEqual([]);
  });
});

describe("cells within the range", () => {
  it("drops anything past the end of the drawn range", () => {
    const cells = [{ pos: 0 }, { pos: 5 }, { pos: 20 }];
    expect(cellsInRange(cells, 6).map((c) => c.pos)).toEqual([0, 5]);
  });

  it("copes with nothing to filter", () => {
    expect(cellsInRange(undefined, 5)).toEqual([]);
  });
});
