import { mulberry32 } from "../rng";

export const SHAPES = ["circle", "square", "triangle", "diamond"];
export const FILLS = ["filled", "outline"];

const CELLS = 9;

// Eight cells share one (shape, fill); the ninth differs in exactly one
// attribute. No colour is used, so the puzzle works for every reader.
export function generate(seed) {
  const rand = mulberry32(seed);
  const pick = (list) => list[Math.floor(rand() * list.length)];

  const base = { shape: pick(SHAPES), fill: pick(FILLS) };
  const odd =
    rand() < 0.5
      ? { shape: pick(SHAPES.filter((s) => s !== base.shape)), fill: base.fill }
      : { shape: base.shape, fill: FILLS.find((f) => f !== base.fill) };

  const oddIndex = Math.floor(rand() * CELLS);
  const cells = Array.from({ length: CELLS }, (_, i) => ({ ...(i === oddIndex ? odd : base) }));
  return { cells, oddIndex };
}

export function isSolved(puzzle, pickedIndex) {
  return pickedIndex === puzzle.oddIndex;
}

export function solve(puzzle) {
  return puzzle.oddIndex;
}
