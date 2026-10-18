// The quick games (odd one out, connect the dots, word ladder / anagram) serve
// several short puzzles in one break so it does not feel over before it
// starts. The count is fixed up front from the logged seed, so a break is
// always finite and its length is recoverable from the event log.

export const MIN_ROUNDS = 3;
export const MAX_ROUNDS = 4;

export function roundCount(game, seed) {
  if (!game || !game.multiRound) return 1;
  return MIN_ROUNDS + (Math.floor(seed / 2) % (MAX_ROUNDS - MIN_ROUNDS + 1));
}

// Round 0 uses the break's own seed. Consecutive seeds alternate the two
// variants of the pattern and word games (grid then sequence, ladder then anagram).
export function roundSeed(seed, round) {
  return (seed + round) >>> 0;
}
