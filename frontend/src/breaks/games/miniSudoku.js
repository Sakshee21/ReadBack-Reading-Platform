import { mulberry32, shuffle } from "../rng";

const N = 4;
const CELLS = 16;
const MIN_GIVENS = 6;
const GIVENS_SPREAD = 3; // each seed keeps between 6 and 8 clues when it can

const BASE = [1, 2, 3, 4, 3, 4, 1, 2, 2, 1, 4, 3, 4, 3, 2, 1];

const UNITS = (() => {
  const units = [];
  for (let i = 0; i < N; i++) {
    units.push([0, 1, 2, 3].map((k) => i * N + k)); // row
    units.push([0, 1, 2, 3].map((k) => k * N + i)); // column
  }
  for (let b = 0; b < N; b++) {
    const r0 = Math.floor(b / 2) * 2;
    const c0 = (b % 2) * 2;
    units.push([r0 * N + c0, r0 * N + c0 + 1, (r0 + 1) * N + c0, (r0 + 1) * N + c0 + 1]); // box
  }
  return units;
})();

const UNITS_OF = Array.from({ length: CELLS }, (_, cell) => UNITS.filter((u) => u.includes(cell)));

function allowed(grid, cell, digit) {
  return UNITS_OF[cell].every((unit) => unit.every((c) => c === cell || grid[c] !== digit));
}

// Counts completions of `grid`, stopping as soon as `limit` is reached.
export function countSolutions(grid, limit = 2) {
  const work = [...grid];
  let count = 0;
  function fill() {
    if (count >= limit) return;
    const cell = work.indexOf(0);
    if (cell === -1) {
      count++;
      return;
    }
    for (let digit = 1; digit <= N; digit++) {
      if (allowed(work, cell, digit)) {
        work[cell] = digit;
        fill();
        work[cell] = 0;
        if (count >= limit) return;
      }
    }
  }
  fill();
  return count;
}

export function conflicts(grid) {
  const flagged = new Set();
  for (const unit of UNITS) {
    const seen = {};
    for (const cell of unit) {
      const v = grid[cell];
      if (v !== 0) (seen[v] ||= []).push(cell);
    }
    for (const cells of Object.values(seen)) {
      if (cells.length > 1) cells.forEach((c) => flagged.add(c));
    }
  }
  return [...flagged].sort((a, b) => a - b);
}

export function isSolved(grid) {
  return grid.length === CELLS && grid.every((v) => v !== 0) && conflicts(grid).length === 0;
}

function shuffledSolution(rand) {
  const digits = shuffle([1, 2, 3, 4], rand);
  const bandOrder = shuffle([0, 1], rand);
  const rowOrder = bandOrder.flatMap((band) => shuffle([0, 1], rand).map((r) => band * 2 + r));
  const stackOrder = shuffle([0, 1], rand);
  const colOrder = stackOrder.flatMap((stack) => shuffle([0, 1], rand).map((c) => stack * 2 + c));
  const transpose = rand() < 0.5;

  const grid = [];
  for (let r = 0; r < N; r++) {
    for (let c = 0; c < N; c++) {
      const src = BASE[rowOrder[r] * N + colOrder[c]];
      grid.push(digits[src - 1]);
    }
  }
  if (!transpose) return grid;
  return grid.map((_, i) => grid[(i % N) * N + Math.floor(i / N)]);
}

export function generate(seed) {
  const rand = mulberry32(seed);
  const solution = shuffledSolution(rand);
  const givens = [...solution];
  const floor = MIN_GIVENS + Math.floor(rand() * GIVENS_SPREAD);
  let remaining = CELLS;

  for (const cell of shuffle([...Array(CELLS).keys()], rand)) {
    if (remaining <= floor) break;
    const kept = givens[cell];
    givens[cell] = 0;
    if (countSolutions(givens) === 1) remaining--;
    else givens[cell] = kept;
  }
  return { givens, solution };
}

// Returns the same grid object when the write is not allowed.
export function setCell(puzzle, grid, index, value) {
  if (!Number.isInteger(index) || index < 0 || index >= CELLS) return grid;
  if (!Number.isInteger(value) || value < 0 || value > N) return grid;
  if (puzzle.givens[index] !== 0) return grid;
  const next = [...grid];
  next[index] = value;
  return next;
}

export function solve(puzzle) {
  return puzzle.solution;
}
