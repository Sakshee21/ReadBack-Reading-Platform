import { describe, expect, it } from "vitest";
import { generate, isSolved, solve } from "./pattern";

describe("pattern (odd_one_out dispatcher)", () => {
  it("uses the odd-one-out grid for even seeds and the sequence for odd seeds", () => {
    expect(generate(2).kind).toBe("odd");
    expect(generate(2).cells).toHaveLength(9);
    expect(generate(3).kind).toBe("next");
    expect(generate(3).options).toHaveLength(4);
  });

  it("solve is accepted by isSolved and no other choice is, for both kinds", () => {
    for (let seed = 0; seed < 100; seed++) {
      const puzzle = generate(seed);
      const choices = puzzle.kind === "odd" ? 9 : 4;
      const right = solve(puzzle);
      for (let i = 0; i < choices; i++) expect(isSolved(puzzle, i)).toBe(i === right);
    }
  });
});
