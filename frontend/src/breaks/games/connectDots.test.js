import { describe, expect, it } from "vitest";
import { SIZE, SYMBOLS, generate, initialState, isComplete, press, solve } from "./connectDots";

const SEEDS = Array.from({ length: 300 }, (_, i) => i);
const adjacent = (a, b) => {
  const dr = Math.abs(Math.floor(a / SIZE) - Math.floor(b / SIZE));
  const dc = Math.abs((a % SIZE) - (b % SIZE));
  return dr + dc === 1;
};

function playPair(puzzle, state, pairIndex) {
  let s = state;
  for (const cell of puzzle.solution[pairIndex]) s = press(puzzle, s, cell);
  return s;
}

describe("connectDots generate", () => {
  it("is deterministic from a seed", () => {
    expect(generate(17)).toEqual(generate(17));
  });

  it("builds valid, solvable boards", () => {
    for (const seed of SEEDS) {
      const puzzle = generate(seed);
      expect(puzzle.size).toBe(5);
      expect([3, 4]).toContain(puzzle.pairs.length);
      const used = new Set();
      puzzle.solution.forEach((path, i) => {
        expect(path.length).toBeGreaterThanOrEqual(4);
        expect(path.length).toBeLessThanOrEqual(7);
        for (let k = 1; k < path.length; k++) expect(adjacent(path[k - 1], path[k])).toBe(true);
        for (const cell of path) {
          expect(used.has(cell)).toBe(false);
          used.add(cell);
        }
        expect(puzzle.pairs[i].ends).toEqual([path[0], path[path.length - 1]]);
        expect(adjacent(path[0], path[path.length - 1])).toBe(false);
      });
      expect(new Set(puzzle.pairs.map((p) => p.symbol)).size).toBe(puzzle.pairs.length);
      for (const p of puzzle.pairs) expect(SYMBOLS).toContain(p.symbol);
    }
  });

  it("solve returns the construction paths", () => {
    const puzzle = generate(4);
    expect(solve(puzzle)).toBe(puzzle.solution);
  });
});

describe("connectDots play", () => {
  it("is not complete at the start and completes after replaying the solution", () => {
    const puzzle = generate(2);
    expect(isComplete(puzzle, initialState(puzzle))).toBe(false);
    let s = initialState(puzzle);
    puzzle.solution.forEach((_, i) => {
      expect(isComplete(puzzle, s)).toBe(false);
      s = playPair(puzzle, s, i);
    });
    expect(isComplete(puzzle, s)).toBe(true);
  });

  it("cannot extend onto another pair's path", () => {
    const puzzle = generate(2);
    const other = puzzle.solution[1];
    const interior = other.slice(1, -1);
    let target = null;
    let from = null;
    for (const b of interior) {
      for (let a = 0; a < SIZE * SIZE; a++) {
        if (adjacent(a, b) && !other.includes(a) && puzzle.pairs.every((p) => !p.ends.includes(a))) {
          target = b;
          from = a;
        }
      }
    }
    expect(target).not.toBeNull();
    const state = { paths: puzzle.pairs.map((_, i) => (i === 1 ? [...other] : i === 0 ? [from] : [])), active: 0 };
    expect(press(puzzle, state, target)).toBe(state);
  });

  it("ignores a press that is not adjacent to the end of the active path", () => {
    const puzzle = generate(2);
    const s = press(puzzle, initialState(puzzle), puzzle.pairs[0].ends[0]);
    const far = [...Array(SIZE * SIZE).keys()].find(
      (c) => !adjacent(c, puzzle.pairs[0].ends[0]) && puzzle.pairs.every((p) => !p.ends.includes(c))
    );
    expect(press(puzzle, s, far)).toBe(s);
  });

  it("pressing an endpoint restarts that pair, even a completed one", () => {
    const puzzle = generate(2);
    const [e0] = puzzle.pairs[0].ends;
    let s = press(puzzle, initialState(puzzle), e0);
    s = press(puzzle, s, puzzle.solution[0][1]);
    expect(s.paths[0]).toHaveLength(2);
    s = press(puzzle, s, e0);
    expect(s.paths[0]).toEqual([e0]);

    let done = initialState(puzzle);
    puzzle.solution.forEach((_, i) => (done = playPair(puzzle, done, i)));
    expect(isComplete(puzzle, done)).toBe(true);
    const restarted = press(puzzle, done, e0);
    expect(restarted.paths[0]).toEqual([e0]);
    expect(isComplete(puzzle, restarted)).toBe(false);
  });

  it("pressing another pair's endpoint switches to that pair", () => {
    const puzzle = generate(2);
    let s = press(puzzle, initialState(puzzle), puzzle.pairs[0].ends[0]);
    s = press(puzzle, s, puzzle.pairs[1].ends[0]);
    expect(s.active).toBe(1);
    expect(s.paths[1]).toEqual([puzzle.pairs[1].ends[0]]);
  });

  it("pressing an earlier cell of the active path truncates it", () => {
    const puzzle = generate(2);
    const path = puzzle.solution[0];
    let s = initialState(puzzle);
    for (const cell of path.slice(0, 3)) s = press(puzzle, s, cell);
    s = press(puzzle, s, path[1]);
    expect(s.paths[0]).toEqual(path.slice(0, 2));
  });

  it("completes a pair only on the other endpoint, and only when adjacent", () => {
    const puzzle = generate(2);
    const path = puzzle.solution[0];
    let s = initialState(puzzle);
    for (const cell of path.slice(0, -2)) s = press(puzzle, s, cell);
    const far = path[path.length - 1];
    expect(press(puzzle, s, far)).toBe(s); // endpoint not adjacent yet
    s = press(puzzle, s, path[path.length - 2]);
    s = press(puzzle, s, far);
    expect(s.active).toBeNull();
    expect(s.paths[0]).toEqual(path);
  });
});

describe("connectDots variety and recovery", () => {
  it("sometimes builds the longest paths", () => {
    const longest = Math.max(...SEEDS.flatMap((s) => generate(s).solution.map((p) => p.length)));
    expect(longest).toBe(7);
  });

  it("almost never needs the fixed fallback layout", () => {
    const fallback = JSON.stringify([[0, 1, 2, 3], [5, 6, 7, 8], [10, 11, 12, 13]]);
    const used = SEEDS.filter((s) => JSON.stringify(generate(s).solution) === fallback).length;
    expect(used / SEEDS.length).toBeLessThan(0.03);
  });

  it("resumes a half-drawn path from its last cell or from any cell on it", () => {
    const puzzle = generate(2);
    const a = puzzle.solution[0];
    let s = initialState(puzzle);
    for (const c of a.slice(0, 3)) s = press(puzzle, s, c);
    s = press(puzzle, s, puzzle.pairs[1].ends[0]); // switch to another pair
    expect(s.active).toBe(1);

    const back = press(puzzle, s, a[2]);
    expect(back.active).toBe(0);
    expect(back.paths[0]).toEqual(a.slice(0, 3));

    const truncated = press(puzzle, s, a[1]);
    expect(truncated.active).toBe(0);
    expect(truncated.paths[0]).toEqual(a.slice(0, 2));
  });

  it("does not edit a completed path from its middle", () => {
    const puzzle = generate(2);
    let s = initialState(puzzle);
    s = playPair(puzzle, s, 0);
    const middle = puzzle.solution[0][1];
    expect(press(puzzle, s, middle)).toBe(s);
  });
});
