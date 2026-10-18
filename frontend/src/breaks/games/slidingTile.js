import { mulberry32 } from "../rng";

export const SOLVED = [1, 2, 3, 4, 5, 6, 7, 8, 0];
const SIZE = 3;
const SCRAMBLE_MOVES = 30;

function adjacent(a, b) {
  const dr = Math.abs(Math.floor(a / SIZE) - Math.floor(b / SIZE));
  const dc = Math.abs((a % SIZE) - (b % SIZE));
  return dr + dc === 1;
}

// Swaps the tile at `index` with the blank when they touch; otherwise returns
// the same array object.
export function move(tiles, index) {
  const blank = tiles.indexOf(0);
  if (!Number.isInteger(index) || index < 0 || index >= tiles.length) return tiles;
  if (index === blank || !adjacent(index, blank)) return tiles;
  const next = [...tiles];
  next[blank] = next[index];
  next[index] = 0;
  return next;
}

export function isSolved(tiles) {
  return tiles.length === SOLVED.length && tiles.every((t, i) => t === SOLVED[i]);
}

export function inversions(tiles) {
  const seq = tiles.filter((t) => t !== 0);
  let count = 0;
  for (let i = 0; i < seq.length; i++) {
    for (let j = i + 1; j < seq.length; j++) if (seq[i] > seq[j]) count++;
  }
  return count;
}

// Scrambling by legal moves from the solved board guarantees solvability.
export function generate(seed) {
  const rand = mulberry32(seed);
  let tiles = [...SOLVED];
  let previousBlank = -1;
  let moves = 0;

  while (moves < SCRAMBLE_MOVES || isSolved(tiles)) {
    const blank = tiles.indexOf(0);
    const options = [];
    for (let i = 0; i < tiles.length; i++) {
      if (i !== blank && i !== previousBlank && adjacent(i, blank)) options.push(i);
    }
    const pick = options[Math.floor(rand() * options.length)];
    previousBlank = blank;
    tiles = move(tiles, pick);
    moves++;
  }
  return { tiles };
}

export function solve() {
  return [...SOLVED];
}
