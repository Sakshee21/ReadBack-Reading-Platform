import { describe, expect, it } from "vitest";
import { conflicts, countSolutions, generate, isSolved, setCell, solve } from "./miniSudoku";

const SEEDS = Array.from({ length: 200 }, (_, i) => i);

const rows = (g) => [0, 1, 2, 3].map((r) => g.slice(r * 4, r * 4 + 4));
const cols = (g) => [0, 1, 2, 3].map((c) => [0, 1, 2, 3].map((r) => g[r * 4 + c]));
const boxes = (g) =>
  [0, 1, 2, 3].map((b) => {
    const r0 = Math.floor(b / 2) * 2;
    const c0 = (b % 2) * 2;
    return [g[r0 * 4 + c0], g[r0 * 4 + c0 + 1], g[(r0 + 1) * 4 + c0], g[(r0 + 1) * 4 + c0 + 1]];
  });
const validUnit = (u) => [...u].sort().join("") === "1234";

describe("miniSudoku generate", () => {
  it("is deterministic from a seed", () => {
    expect(generate(31)).toEqual(generate(31));
  });

  it("has a valid solution", () => {
    for (const seed of SEEDS) {
      const { solution } = generate(seed);
      for (const unit of [...rows(solution), ...cols(solution), ...boxes(solution)]) {
        expect(validUnit(unit)).toBe(true);
      }
    }
  });

  it("has exactly one solution that agrees with the givens", () => {
    for (const seed of SEEDS) {
      const { givens, solution } = generate(seed);
      expect(countSolutions(givens)).toBe(1);
      givens.forEach((v, i) => {
        if (v !== 0) expect(solution[i]).toBe(v);
      });
    }
  });

  it("keeps between 6 and 10 givens", () => {
    for (const seed of SEEDS) {
      const count = generate(seed).givens.filter((v) => v !== 0).length;
      expect(count).toBeGreaterThanOrEqual(6);
      expect(count).toBeLessThanOrEqual(10);
    }
  });

  it("varies the difficulty between seeds", () => {
    const counts = new Set(SEEDS.map((s) => generate(s).givens.filter((v) => v !== 0).length));
    expect(counts.size).toBeGreaterThanOrEqual(3);
  });

  it("solve returns the solution", () => {
    const puzzle = generate(5);
    expect(solve(puzzle)).toBe(puzzle.solution);
  });
});

describe("miniSudoku rules", () => {
  const empty = Array(16).fill(0);

  it("flags duplicates in a row, a column and a box", () => {
    const row = [...empty];
    row[0] = 1;
    row[3] = 1;
    expect(conflicts(row)).toEqual([0, 3]);

    const col = [...empty];
    col[1] = 2;
    col[13] = 2;
    expect(conflicts(col)).toEqual([1, 13]);

    const box = [...empty];
    box[0] = 3;
    box[5] = 3;
    expect(conflicts(box)).toEqual([0, 5]);
  });

  it("never flags empty cells and accepts a valid partial grid", () => {
    expect(conflicts(empty)).toEqual([]);
    const partial = [...empty];
    partial[0] = 1;
    partial[1] = 2;
    partial[4] = 3;
    expect(conflicts(partial)).toEqual([]);
  });

  it("is solved only when complete and valid", () => {
    const { solution } = generate(3);
    expect(isSolved(solution)).toBe(true);
    const cleared = [...solution];
    cleared[0] = 0;
    expect(isSolved(cleared)).toBe(false);
    const swapped = [...solution];
    [swapped[0], swapped[1]] = [swapped[1], swapped[0]];
    expect(isSolved(swapped)).toBe(false);
  });
});

describe("miniSudoku setCell", () => {
  it("ignores givens, bad indexes and bad values", () => {
    const puzzle = generate(6);
    const grid = [...puzzle.givens];
    const givenIndex = grid.findIndex((v) => v !== 0);
    const free = grid.findIndex((v) => v === 0);
    expect(setCell(puzzle, grid, givenIndex, 1)).toBe(grid);
    expect(setCell(puzzle, grid, -1, 1)).toBe(grid);
    expect(setCell(puzzle, grid, 16, 1)).toBe(grid);
    expect(setCell(puzzle, grid, free, 5)).toBe(grid);
    expect(setCell(puzzle, grid, free, 1.5)).toBe(grid);
    expect(setCell(puzzle, grid, free, "2")).toBe(grid);
  });

  it("writes and clears without touching the original", () => {
    const puzzle = generate(6);
    const grid = [...puzzle.givens];
    const free = grid.findIndex((v) => v === 0);
    const written = setCell(puzzle, grid, free, 3);
    expect(written[free]).toBe(3);
    expect(grid[free]).toBe(0);
    expect(setCell(puzzle, written, free, 0)[free]).toBe(0);
  });
});
