import { describe, expect, it } from "vitest";
import { generate, isSolved, solve } from "./oddOneOut";

const SEEDS = Array.from({ length: 200 }, (_, i) => i);
const same = (a, b) => a.shape === b.shape && a.fill === b.fill;

describe("oddOneOut", () => {
  it("is deterministic for a seed", () => {
    expect(generate(123)).toEqual(generate(123));
  });

  it("has nine cells with exactly one cell off from the other eight", () => {
    for (const seed of SEEDS) {
      const { cells, oddIndex } = generate(seed);
      expect(cells).toHaveLength(9);
      const odd = cells[oddIndex];
      const others = cells.filter((_, i) => i !== oddIndex);
      for (const c of others) expect(same(c, others[0])).toBe(true);
      expect(same(odd, others[0])).toBe(false);
    }
  });

  it("differs from the rest in exactly one attribute", () => {
    for (const seed of SEEDS) {
      const { cells, oddIndex } = generate(seed);
      const base = cells[oddIndex === 0 ? 1 : 0];
      const odd = cells[oddIndex];
      const diffs = Number(odd.shape !== base.shape) + Number(odd.fill !== base.fill);
      expect(diffs).toBe(1);
    }
  });

  it("puts the odd cell in varied positions", () => {
    const positions = new Set(SEEDS.map((s) => generate(s).oddIndex));
    expect(positions.size).toBeGreaterThanOrEqual(6);
  });

  it("is solved only by picking the odd cell", () => {
    const puzzle = generate(7);
    for (let i = 0; i < 9; i++) expect(isSolved(puzzle, i)).toBe(i === puzzle.oddIndex);
    expect(isSolved(puzzle, -1)).toBe(false);
    expect(isSolved(puzzle, 9)).toBe(false);
  });

  it("solve returns the odd index", () => {
    const puzzle = generate(8);
    expect(solve(puzzle)).toBe(puzzle.oddIndex);
  });
});
