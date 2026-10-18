import { mulberry32, shuffle } from "../rng";
import { FILLS, SHAPES } from "./oddOneOut";

const SEQUENCE_LENGTH = 4;
const OPTIONS = 4;

// Rule: shapes repeat with a period of 2 or 3, and the fill alternates on
// every item. No colour is used.
export function generate(seed) {
  const rand = mulberry32(seed);
  const period = rand() < 0.5 ? 2 : 3;
  const cycle = shuffle(SHAPES, rand).slice(0, period);
  const startsFilled = rand() < 0.5;

  const item = (i) => ({
    shape: cycle[i % period],
    fill: (i % 2 === 0) === startsFilled ? "filled" : "outline",
  });

  const sequence = Array.from({ length: SEQUENCE_LENGTH }, (_, i) => item(i));
  const correct = item(SEQUENCE_LENGTH);

  const all = SHAPES.flatMap((shape) => FILLS.map((fill) => ({ shape, fill })));
  const distractors = shuffle(
    all.filter((c) => c.shape !== correct.shape || c.fill !== correct.fill),
    rand
  ).slice(0, OPTIONS - 1);

  const answerIndex = Math.floor(rand() * OPTIONS);
  const options = [...distractors];
  options.splice(answerIndex, 0, correct);
  return { sequence, options, answerIndex };
}

export function isSolved(puzzle, pickedIndex) {
  return pickedIndex === puzzle.answerIndex;
}

export function solve(puzzle) {
  return puzzle.answerIndex;
}
