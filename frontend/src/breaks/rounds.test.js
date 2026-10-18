import { describe, expect, it } from "vitest";
import { GAMES } from "./registry";
import { roundCount, roundSeed } from "./rounds";

const SEEDS = Array.from({ length: 100 }, (_, i) => i);
const byId = (id) => GAMES.find((g) => g.id === id);

describe("roundCount", () => {
  it("serves three or four puzzles for the quick games, and both occur", () => {
    for (const id of ["odd_one_out", "connect_dots", "word_play"]) {
      const counts = SEEDS.map((s) => roundCount(byId(id), s));
      expect(counts.every((n) => n === 3 || n === 4)).toBe(true);
      expect(new Set(counts)).toEqual(new Set([3, 4]));
    }
  });

  it("serves exactly one puzzle for the longer games", () => {
    for (const id of ["matching_cards", "sliding_tile", "mini_sudoku"]) {
      expect(SEEDS.every((s) => roundCount(byId(id), s) === 1)).toBe(true);
    }
  });

  it("is decided by the logged seed alone", () => {
    expect(roundCount(byId("word_play"), 12345)).toBe(roundCount(byId("word_play"), 12345));
  });

  it("flags exactly the three quick games as multi-round", () => {
    expect(GAMES.filter((g) => g.multiRound).map((g) => g.id).sort()).toEqual([
      "connect_dots",
      "odd_one_out",
      "word_play",
    ]);
  });
});

describe("roundSeed", () => {
  it("starts from the break's own seed", () => {
    expect(roundSeed(777, 0)).toBe(777);
    expect(roundSeed(777, 2)).toBe(779);
  });

  it("stays a valid uint32 at the top of the range", () => {
    const s = roundSeed(4294967295, 3);
    expect(Number.isInteger(s)).toBe(true);
    expect(s).toBeGreaterThanOrEqual(0);
    expect(s).toBeLessThan(2 ** 32);
  });

  it("alternates the two variants of a game from one round to the next", () => {
    for (const id of ["odd_one_out", "word_play"]) {
      const game = byId(id);
      for (const seed of [2, 3, 10, 11, 1000]) {
        expect(game.generate(roundSeed(seed, 0)).kind).not.toBe(game.generate(roundSeed(seed, 1)).kind);
      }
    }
  });
});
