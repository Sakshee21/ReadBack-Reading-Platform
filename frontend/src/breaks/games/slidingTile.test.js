import { describe, expect, it } from "vitest";
import { SOLVED, generate, inversions, isSolved, move, solve } from "./slidingTile";

describe("slidingTile", () => {
  it("is deterministic from a seed", () => {
    expect(generate(11)).toEqual(generate(11));
  });

  it("is always a permutation, never solved, and always solvable", () => {
    for (let seed = 0; seed < 500; seed++) {
      const { tiles } = generate(seed);
      expect([...tiles].sort((a, b) => a - b)).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8]);
      expect(isSolved(tiles)).toBe(false);
      expect(inversions(tiles) % 2).toBe(0);
    }
  });

  it("swaps an adjacent tile with the blank", () => {
    const tiles = [1, 2, 3, 4, 5, 6, 7, 0, 8];
    expect(move(tiles, 8)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 0]);
    const centre = [1, 2, 3, 4, 0, 5, 6, 7, 8];
    for (const i of [1, 3, 5, 7]) {
      const out = move(centre, i);
      expect(out[4]).toBe(centre[i]);
      expect(out[i]).toBe(0);
    }
  });

  it("ignores non-adjacent tiles and the blank itself", () => {
    const tiles = [1, 2, 3, 4, 5, 6, 7, 8, 0];
    expect(move(tiles, 0)).toBe(tiles);
    expect(move(tiles, 8)).toBe(tiles);
  });

  it("does not wrap around row ends", () => {
    const blankAt3 = [1, 2, 3, 0, 4, 5, 6, 7, 8];
    expect(move(blankAt3, 2)).toBe(blankAt3);
    const blankAt2 = [1, 2, 0, 3, 4, 5, 6, 7, 8];
    expect(move(blankAt2, 3)).toBe(blankAt2);
  });

  it("recognises the solved board", () => {
    expect(isSolved(SOLVED)).toBe(true);
    expect(isSolved([1, 2, 3, 4, 5, 6, 7, 0, 8])).toBe(false);
    expect(solve(generate(1))).toEqual(SOLVED);
  });

  it("does not mutate its input", () => {
    const tiles = [1, 2, 3, 4, 5, 6, 7, 0, 8];
    const copy = [...tiles];
    move(tiles, 8);
    expect(tiles).toEqual(copy);
  });
});
