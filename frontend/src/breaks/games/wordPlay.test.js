import { describe, expect, it } from "vitest";
import { ANAGRAMS, LADDERS, WORDS } from "./wordData";
import {
  checkAnagram,
  differsByOne,
  generate,
  hint,
  normalize,
  shortestPath,
  solve,
  tryStep,
} from "./wordPlay";

const SEEDS = Array.from({ length: 200 }, (_, i) => i);
const sorted = (w) => [...w].sort().join("");

describe("word data", () => {
  it("has a clean 4-letter word list", () => {
    expect(WORDS.length).toBeGreaterThanOrEqual(150);
    expect(new Set(WORDS).size).toBe(WORDS.length);
    for (const w of WORDS) expect(w).toMatch(/^[a-z]{4}$/);
  });

  it("has ladders that are solvable in three or four steps", () => {
    expect(LADDERS.length).toBeGreaterThanOrEqual(8);
    for (const { start, target } of LADDERS) {
      expect(WORDS).toContain(start);
      expect(WORDS).toContain(target);
      const path = shortestPath(start, target);
      expect(path).not.toBeNull();
      expect([4, 5]).toContain(path.length);
      for (let i = 1; i < path.length; i++) expect(differsByOne(path[i - 1], path[i])).toBe(true);
    }
  });

  it("has anagram words with a single arrangement in the list", () => {
    expect(ANAGRAMS.length).toBeGreaterThanOrEqual(25);
    for (const w of ANAGRAMS) expect(w).toMatch(/^[a-z]{5}$/);
    expect(new Set(ANAGRAMS.map(sorted)).size).toBe(ANAGRAMS.length);
  });
});

describe("generate", () => {
  it("is deterministic from a seed", () => {
    expect(generate(12)).toEqual(generate(12));
  });

  it("gives a ladder for even seeds and an anagram for odd seeds", () => {
    expect(generate(0).kind).toBe("ladder");
    expect(generate(1).kind).toBe("anagram");
    expect(generate(0).path.length).toBeGreaterThanOrEqual(4);
  });

  it("scrambles into a different permutation of the same letters", () => {
    for (const seed of SEEDS.filter((s) => s % 2 === 1)) {
      const p = generate(seed);
      expect(sorted(p.scrambled)).toBe(sorted(p.word));
      expect(p.scrambled).not.toBe(p.word);
    }
  });
});

describe("ladder rules", () => {
  it("accepts every step of the shortest path and detects the solve at the end", () => {
    const puzzle = generate(0);
    let chain = [puzzle.start];
    puzzle.path.slice(1).forEach((word, i, rest) => {
      const result = tryStep(puzzle, chain, word);
      expect(result.ok).toBe(true);
      expect(result.solved).toBe(i === rest.length - 1);
      chain = result.chain;
    });
    expect(chain).toEqual(puzzle.path);
  });

  it("rejects bad steps with a reason and normalises the input", () => {
    const puzzle = generate(0);
    const chain = [puzzle.start];
    expect(tryStep(puzzle, chain, "abc")).toEqual({ ok: false, reason: "length" });
    expect(tryStep(puzzle, chain, "xxxx")).toEqual({ ok: false, reason: "not_a_word" });
    const farWord = WORDS.find((w) => !differsByOne(w, puzzle.start) && w !== puzzle.start);
    expect(tryStep(puzzle, chain, farWord)).toEqual({ ok: false, reason: "not_one_letter" });
    const next = puzzle.path[1];
    const after = tryStep(puzzle, chain, `  ${next.toUpperCase()} `);
    expect(after.ok).toBe(true);
    expect(tryStep(puzzle, after.chain, puzzle.start)).toEqual({ ok: false, reason: "repeat" });
  });

  it("normalize trims and lower-cases", () => {
    expect(normalize("  AbC ")).toBe("abc");
  });
});

describe("anagram rules", () => {
  it("checks the answer after normalising", () => {
    const puzzle = generate(1);
    expect(checkAnagram(puzzle, ` ${puzzle.word.toUpperCase()} `)).toBe(true);
    expect(checkAnagram(puzzle, puzzle.scrambled)).toBe(false);
    expect(checkAnagram(puzzle, "")).toBe(false);
  });
});

describe("hint and solve", () => {
  it("gives the next ladder word or the first anagram letter", () => {
    const ladder = generate(0);
    expect(hint(ladder, [ladder.start])).toBe(ladder.path[1]);
    const anagram = generate(1);
    expect(hint(anagram)).toBe(anagram.word[0]);
  });

  it("solve returns the path or the word", () => {
    expect(solve(generate(0))).toEqual(generate(0).path);
    expect(solve(generate(1))).toBe(generate(1).word);
  });

  it("never hints at a word that is already in the chain", () => {
    for (const { start, target } of LADDERS) {
      const puzzle = { kind: "ladder", start, target, path: shortestPath(start, target) };
      for (const first of WORDS.filter((w) => differsByOne(w, start))) {
        const chain = [start, first];
        const next = hint(puzzle, chain);
        if (next !== null) {
          expect(chain).not.toContain(next);
          expect(differsByOne(first, next)).toBe(true);
        }
      }
    }
  });

  it("returns null when the chain has no way forward", () => {
    // Every one-letter neighbour of "soap" is already used, so nothing is left to step onto.
    const puzzle = { kind: "ladder", start: "soap", target: "rock", path: shortestPath("soap", "rock") };
    const neighbours = WORDS.filter((w) => differsByOne(w, "soap"));
    expect(neighbours.length).toBeGreaterThan(0);
    expect(hint(puzzle, [...neighbours, "soap"])).toBeNull();
  });
});

describe("word list quality", () => {
  it("includes everyday words and leaves out obscure ones", () => {
    for (const w of ["mold", "mood", "back", "ship"]) expect(WORDS).toContain(w);
    for (const w of ["bane", "dole", "cove", "hemp", "bile", "wade"]) expect(WORDS).not.toContain(w);
  });

  it("has no word that cannot be part of any ladder", () => {
    for (const w of WORDS) expect(WORDS.some((o) => differsByOne(w, o))).toBe(true);
  });
});
