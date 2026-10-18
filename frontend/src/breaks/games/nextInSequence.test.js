import { describe, expect, it } from "vitest";
import { generate, isSolved, solve } from "./nextInSequence";

const SEEDS = Array.from({ length: 200 }, (_, i) => i);
const key = (c) => `${c.shape}|${c.fill}`;

// The rule: shapes repeat with period 2 or 3, fill alternates every item.
function continuation(sequence) {
  const period = [2, 3].find((p) => sequence.every((c, i) => c.shape === sequence[i % p].shape));
  const next = sequence.length;
  const fill = sequence[0].fill === "filled" ? (next % 2 === 0 ? "filled" : "outline") : next % 2 === 0 ? "outline" : "filled";
  return { shape: sequence[next % period].shape, fill };
}

describe("nextInSequence", () => {
  it("is deterministic from a seed", () => {
    expect(generate(21)).toEqual(generate(21));
  });

  it("has a four-item sequence and exactly one option continuing it", () => {
    for (const seed of SEEDS) {
      const puzzle = generate(seed);
      expect(puzzle.sequence).toHaveLength(4);
      const want = key(continuation(puzzle.sequence));
      const matches = puzzle.options.map(key).filter((k) => k === want);
      expect(matches).toHaveLength(1);
      expect(key(puzzle.options[puzzle.answerIndex])).toBe(want);
    }
  });

  it("offers four distinct options", () => {
    for (const seed of SEEDS) {
      const { options } = generate(seed);
      expect(options).toHaveLength(4);
      expect(new Set(options.map(key)).size).toBe(4);
    }
  });

  it("is solved only by the answer", () => {
    const puzzle = generate(8);
    for (let i = 0; i < 4; i++) expect(isSolved(puzzle, i)).toBe(i === puzzle.answerIndex);
    expect(solve(puzzle)).toBe(puzzle.answerIndex);
  });

  it("varies where the answer sits", () => {
    expect(new Set(SEEDS.map((s) => generate(s).answerIndex)).size).toBeGreaterThanOrEqual(3);
  });
});
