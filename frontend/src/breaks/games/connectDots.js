import { mulberry32 } from "../rng";

export const SIZE = 5;
export const SYMBOLS = ["●", "■", "▲", "◆"];
export const SYMBOL_NAMES = ["circle", "square", "triangle", "diamond"];

const CELLS = SIZE * SIZE;
const MIN_LEN = 4;
const MAX_LEN = 7;
const ATTEMPTS = 500;

function adjacent(a, b) {
  const dr = Math.abs(Math.floor(a / SIZE) - Math.floor(b / SIZE));
  const dc = Math.abs((a % SIZE) - (b % SIZE));
  return dr + dc === 1;
}

function neighbours(cell) {
  const r = Math.floor(cell / SIZE);
  const c = cell % SIZE;
  const out = [];
  if (r > 0) out.push(cell - SIZE);
  if (r < SIZE - 1) out.push(cell + SIZE);
  if (c > 0) out.push(cell - 1);
  if (c < SIZE - 1) out.push(cell + 1);
  return out;
}

// One random self-avoiding walk over free cells; null if it gets stuck.
function walk(rand, used, length) {
  const free = [...Array(CELLS).keys()].filter((c) => !used.has(c));
  if (free.length < length) return null;
  const path = [free[Math.floor(rand() * free.length)]];
  const taken = new Set(used);
  taken.add(path[0]);
  while (path.length < length) {
    const options = neighbours(path[path.length - 1]).filter((c) => !taken.has(c));
    if (options.length === 0) return null;
    const next = options[Math.floor(rand() * options.length)];
    path.push(next);
    taken.add(next);
  }
  return path;
}

function layout(rand) {
  const count = rand() < 0.5 ? 3 : 4;
  const used = new Set();
  const paths = [];
  for (let i = 0; i < count; i++) {
    const length = MIN_LEN + Math.floor(rand() * (MAX_LEN - MIN_LEN + 1));
    const path = walk(rand, used, length);
    if (!path || adjacent(path[0], path[path.length - 1])) return null;
    path.forEach((c) => used.add(c));
    paths.push(path);
  }
  return paths;
}

// Boards are built from the paths of their own solution, so every board is
// solvable by construction. A fixed three-row layout is the last resort.
export function generate(seed) {
  const rand = mulberry32(seed);
  let solution = null;
  for (let attempt = 0; attempt < ATTEMPTS && !solution; attempt++) solution = layout(rand);
  if (!solution) solution = [[0, 1, 2, 3], [5, 6, 7, 8], [10, 11, 12, 13]];

  const pairs = solution.map((path, id) => ({
    id,
    symbol: SYMBOLS[id],
    ends: [path[0], path[path.length - 1]],
  }));
  return { size: SIZE, pairs, solution };
}

export function initialState(puzzle) {
  return { paths: puzzle.pairs.map(() => []), active: null };
}

const withPath = (state, pair, path, active) => ({
  paths: state.paths.map((p, i) => (i === pair ? path : p)),
  active,
});

// Returns the same state object whenever a press is ignored.
export function press(puzzle, state, cell) {
  if (!Number.isInteger(cell) || cell < 0 || cell >= CELLS) return state;

  const endpointOf = puzzle.pairs.findIndex((p) => p.ends.includes(cell));
  if (endpointOf !== -1) {
    const path = state.paths[endpointOf];
    if (state.active === endpointOf && path.length > 0) {
      if (cell !== path[0] && adjacent(path[path.length - 1], cell)) {
        return withPath(state, endpointOf, [...path, cell], null);
      }
      if (cell !== path[0]) return state;
    }
    if (path.length === 1 && path[0] === cell && state.active === endpointOf) return state;
    return withPath(state, endpointOf, [cell], endpointOf);
  }

  // A cell on an unfinished path: resume that pair from there (this also lets
  // a player pick a half-drawn path back up after switching to another pair).
  const owner = state.paths.findIndex((p) => p.includes(cell));
  if (owner !== -1) {
    if (pairConnected(puzzle, state, owner)) return state;
    const path = state.paths[owner];
    const at = path.indexOf(cell);
    if (owner === state.active && at === path.length - 1) return state;
    return withPath(state, owner, path.slice(0, at + 1), owner);
  }

  if (state.active === null) return state;
  const path = state.paths[state.active];
  if (adjacent(path[path.length - 1], cell)) {
    return withPath(state, state.active, [...path, cell], state.active);
  }
  return state;
}

function pairConnected(puzzle, state, i) {
  const path = state.paths[i];
  if (path.length < 2) return false;
  const first = path[0];
  const last = path[path.length - 1];
  return first !== last && puzzle.pairs[i].ends.includes(first) && puzzle.pairs[i].ends.includes(last);
}

export function isComplete(puzzle, state) {
  return puzzle.pairs.every((_, i) => pairConnected(puzzle, state, i));
}

export function solve(puzzle) {
  return puzzle.solution;
}
