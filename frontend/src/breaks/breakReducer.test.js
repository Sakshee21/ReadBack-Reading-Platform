import { describe, expect, it } from "vitest";
import { breakReducer, initialBreakState } from "./breakReducer";

const run = (state, ...actions) => actions.reduce(breakReducer, state);

describe("breakReducer", () => {
  it("walks the happy path from idle back to idle", () => {
    let s = run(initialBreakState, { type: "MARK_DUE" });
    expect(s.phase).toBe("due");
    s = run(s, { type: "SHOW_OFFER" });
    expect(s.phase).toBe("offered");
    s = run(s, { type: "ACCEPT", gameId: "odd_one_out", seed: 5 });
    expect(s).toMatchObject({ phase: "playing", gameId: "odd_one_out", seed: 5 });
    s = run(s, { type: "FINISH", outcome: "solved" });
    expect(s).toMatchObject({ phase: "ended", outcome: "solved" });
    s = run(s, { type: "DONE" });
    expect(s).toEqual(initialBreakState);
  });

  it("returns to idle when the offer is declined", () => {
    const s = run(initialBreakState, { type: "MARK_DUE" }, { type: "SHOW_OFFER" }, { type: "DECLINE" });
    expect(s).toEqual(initialBreakState);
  });

  it("returns the same state object for invalid transitions", () => {
    expect(breakReducer(initialBreakState, { type: "ACCEPT", gameId: "x", seed: 1 })).toBe(initialBreakState);
    expect(breakReducer(initialBreakState, { type: "SHOW_OFFER" })).toBe(initialBreakState);
    const playing = run(
      initialBreakState,
      { type: "MARK_DUE" },
      { type: "SHOW_OFFER" },
      { type: "ACCEPT", gameId: "g", seed: 1 }
    );
    expect(breakReducer(playing, { type: "DONE" })).toBe(playing);
    expect(breakReducer(playing, { type: "MARK_DUE" })).toBe(playing);
  });

  it("ignores a second FINISH so one outcome is recorded", () => {
    const playing = run(
      initialBreakState,
      { type: "MARK_DUE" },
      { type: "SHOW_OFFER" },
      { type: "ACCEPT", gameId: "g", seed: 1 }
    );
    const ended = breakReducer(playing, { type: "FINISH", outcome: "solved" });
    const again = breakReducer(ended, { type: "FINISH", outcome: "time_cap" });
    expect(again).toBe(ended);
    expect(again.outcome).toBe("solved");
  });

  it("rejects unknown outcomes", () => {
    const playing = run(
      initialBreakState,
      { type: "MARK_DUE" },
      { type: "SHOW_OFFER" },
      { type: "ACCEPT", gameId: "g", seed: 1 }
    );
    expect(breakReducer(playing, { type: "FINISH", outcome: "won" })).toBe(playing);
  });
});
