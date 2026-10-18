import { describe, expect, it } from "vitest";
import { SYMBOLS, clearMismatch, flip, generate, initialState, isComplete, solve } from "./matchingCards";

const SEEDS = Array.from({ length: 200 }, (_, i) => i);

// index pairs of equal symbols for a puzzle
function pairsOf(puzzle) {
  const by = {};
  puzzle.cards.forEach((c, i) => (by[c.symbol] ||= []).push(i));
  return Object.values(by);
}
function mismatchPair(puzzle) {
  const [a] = pairsOf(puzzle)[0];
  const [b] = pairsOf(puzzle)[1];
  return [a, b];
}

describe("matchingCards", () => {
  it("is deterministic from a seed", () => {
    expect(generate(5)).toEqual(generate(5));
  });

  it("has twelve cards forming six pairs", () => {
    for (const seed of SEEDS) {
      const { cards } = generate(seed);
      expect(cards).toHaveLength(12);
      const counts = {};
      for (const c of cards) counts[c.symbol] = (counts[c.symbol] || 0) + 1;
      expect(Object.keys(counts)).toHaveLength(6);
      expect(Object.values(counts).every((n) => n === 2)).toBe(true);
    }
  });

  it("marks a matching pair as matched", () => {
    const puzzle = generate(3);
    const [a, b] = pairsOf(puzzle)[0];
    const s = flip(puzzle, flip(puzzle, initialState(), a), b);
    expect(s.matched.sort()).toEqual([a, b].sort());
    expect(s.faceUp).toEqual([]);
    expect(s.pending).toBeNull();
  });

  it("sets pending on a mismatch and blocks a third flip", () => {
    const puzzle = generate(3);
    const [a, b] = mismatchPair(puzzle);
    const s = flip(puzzle, flip(puzzle, initialState(), a), b);
    expect(s.pending).toEqual([a, b]);
    const other = [...Array(12).keys()].find((i) => i !== a && i !== b);
    expect(flip(puzzle, s, other)).toBe(s);
  });

  it("turns mismatched cards back on clearMismatch", () => {
    const puzzle = generate(3);
    const [a, b] = mismatchPair(puzzle);
    const mismatched = flip(puzzle, flip(puzzle, initialState(), a), b);
    const cleared = clearMismatch(mismatched);
    expect(cleared.faceUp).toEqual([]);
    expect(cleared.pending).toBeNull();
    expect(cleared.matched).toEqual(mismatched.matched);
  });

  it("ignores repeated, matched and out-of-range flips", () => {
    const puzzle = generate(3);
    const [a, b] = pairsOf(puzzle)[0];
    const once = flip(puzzle, initialState(), a);
    expect(flip(puzzle, once, a)).toBe(once);
    const matched = flip(puzzle, once, b);
    expect(flip(puzzle, matched, a)).toBe(matched);
    expect(flip(puzzle, initialState(), -1)).toEqual(initialState());
    const s = initialState();
    expect(flip(puzzle, s, -1)).toBe(s);
    expect(flip(puzzle, s, 12)).toBe(s);
  });

  it("is complete only after every pair is matched", () => {
    const puzzle = generate(9);
    let s = initialState();
    const pairs = pairsOf(puzzle);
    pairs.forEach(([a, b], n) => {
      expect(isComplete(puzzle, s)).toBe(false);
      s = flip(puzzle, flip(puzzle, s, a), b);
      expect(isComplete(puzzle, s)).toBe(n === pairs.length - 1);
    });
  });

  it("clearMismatch without a pending mismatch is a no-op", () => {
    const s = initialState();
    expect(clearMismatch(s)).toBe(s);
  });

  it("solve lists every card", () => {
    expect(solve(generate(1))).toEqual([...Array(12).keys()]);
  });

  it("uses distinct glyphs that render as text, not colour emoji or missing boxes", () => {
    expect(new Set(SYMBOLS.map((x) => x.glyph)).size).toBe(SYMBOLS.length);
    expect(new Set(SYMBOLS.map((x) => x.name)).size).toBe(SYMBOLS.length);
    for (const { glyph } of SYMBOLS) {
      const code = glyph.codePointAt(0);
      // Dingbats are patchy across fonts and some default to emoji
      expect(code >= 0x2700 && code <= 0x27bf).toBe(false);
      // Miscellaneous Symbols can render as colour emoji unless forced to text
      if (code >= 0x2600 && code <= 0x26ff) expect(glyph.endsWith("\uFE0E") || code === 0x263e).toBe(true);
    }
  });
});
