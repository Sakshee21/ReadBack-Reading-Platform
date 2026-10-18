import * as oddOneOut from "./oddOneOut";
import * as nextInSequence from "./nextInSequence";

// The registered `odd_one_out` game: even seeds give the odd-one-out grid,
// odd seeds give the "what comes next" sequence. The seed is logged with
// break_game_start, so the variant is recoverable from the event log.
export function generate(seed) {
  return seed % 2 === 0
    ? { kind: "odd", ...oddOneOut.generate(seed) }
    : { kind: "next", ...nextInSequence.generate(seed) };
}

export function isSolved(puzzle, pickedIndex) {
  return puzzle.kind === "odd"
    ? oddOneOut.isSolved(puzzle, pickedIndex)
    : nextInSequence.isSolved(puzzle, pickedIndex);
}

export function solve(puzzle) {
  return puzzle.kind === "odd" ? oddOneOut.solve(puzzle) : nextInSequence.solve(puzzle);
}
