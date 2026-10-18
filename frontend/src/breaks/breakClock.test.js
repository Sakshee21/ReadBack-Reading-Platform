import { describe, expect, it } from "vitest";
import {
  clockDay,
  evaluateBreak,
  initialClock,
  loadClock,
  recordOffer,
  recordSessionComplete,
  recordSessionStart,
  saveClock,
} from "./breakClock";
import { AWAY_RESET_MS, BREAK_AFTER_ACTIVE_MS, MAX_OFFERS_PER_DAY } from "./constants";

const NOW = new Date(2026, 9, 18, 15, 0, 0).getTime();
const base = { finished: false, quizDue: false, enabled: true, now: NOW };
const withActive = (activeMs) => ({ ...initialClock(), activeMs });

function memoryStorage(initial = {}) {
  const data = { ...initial };
  return {
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => {
      data[k] = v;
    },
    data,
  };
}

describe("evaluateBreak", () => {
  it("is not due below the threshold and due at it", () => {
    expect(evaluateBreak(withActive(9 * 60_000), base).due).toBe(false);
    expect(evaluateBreak(withActive(BREAK_AFTER_ACTIVE_MS), base).due).toBe(true);
  });

  it("defers without changing the clock when a quiz is due", () => {
    const clock = withActive(BREAK_AFTER_ACTIVE_MS + 1);
    const snapshot = JSON.stringify(clock);
    expect(evaluateBreak(clock, { ...base, quizDue: true })).toEqual({
      due: false,
      deferredReason: "quiz_due",
    });
    expect(JSON.stringify(clock)).toBe(snapshot);
  });

  it("is never due when the book is finished or breaks are disabled", () => {
    const clock = withActive(BREAK_AFTER_ACTIVE_MS * 2);
    expect(evaluateBreak(clock, { ...base, finished: true }).due).toBe(false);
    expect(evaluateBreak(clock, { ...base, enabled: false }).due).toBe(false);
  });

  it("stops offering after the daily cap", () => {
    let clock = initialClock();
    for (let i = 0; i < MAX_OFFERS_PER_DAY; i++) clock = recordOffer(clock, NOW);
    clock = { ...clock, activeMs: BREAK_AFTER_ACTIVE_MS * 2 };
    expect(evaluateBreak(clock, base).due).toBe(false);
  });

  it("lets yesterday's offers expire at local midnight", () => {
    const yesterday = clockDay(NOW - 24 * 60 * 60 * 1000);
    const clock = {
      ...initialClock(),
      activeMs: BREAK_AFTER_ACTIVE_MS,
      offersToday: MAX_OFFERS_PER_DAY,
      offersDay: yesterday,
    };
    expect(evaluateBreak(clock, base).due).toBe(true);
  });
});

describe("recordSessionComplete", () => {
  it("accumulates active time and stamps the end time", () => {
    let clock = recordSessionComplete(initialClock(), 120_000, NOW);
    clock = recordSessionComplete(clock, 120_000, NOW + 1);
    expect(clock.activeMs).toBe(240_000);
    expect(clock.lastSessionEndAt).toBe(NOW + 1);
  });

  it("ignores non-finite or negative values", () => {
    const clock = withActive(1000);
    for (const bad of [NaN, -5, undefined, null, Infinity, "x"]) {
      expect(recordSessionComplete(clock, bad, NOW).activeMs).toBe(1000);
    }
  });

  it("clamps one huge addition to two hours", () => {
    expect(recordSessionComplete(initialClock(), 10 * 60 * 60_000, NOW).activeMs).toBe(7_200_000);
  });
});

describe("recordOffer", () => {
  it("resets active time and counts the offer", () => {
    const clock = recordOffer(withActive(BREAK_AFTER_ACTIVE_MS), NOW);
    expect(clock.activeMs).toBe(0);
    expect(clock.offersToday).toBe(1);
    expect(clock.offersDay).toBe(clockDay(NOW));
  });
});

describe("recordSessionStart", () => {
  it("resets active time after an away gap of five minutes", () => {
    const clock = { ...withActive(300_000), lastSessionEndAt: NOW - AWAY_RESET_MS };
    expect(recordSessionStart(clock, NOW).activeMs).toBe(0);
  });

  it("keeps active time for a shorter gap", () => {
    const clock = { ...withActive(300_000), lastSessionEndAt: NOW - (AWAY_RESET_MS - 1000) };
    expect(recordSessionStart(clock, NOW).activeMs).toBe(300_000);
  });

  it("keeps active time when there was no previous session", () => {
    expect(recordSessionStart(withActive(300_000), NOW).activeMs).toBe(300_000);
  });
});

describe("storage", () => {
  const KEY = "k";

  it("round-trips through storage", () => {
    const storage = memoryStorage();
    const clock = recordOffer(withActive(5000), NOW);
    saveClock(storage, KEY, clock);
    expect(loadClock(storage, KEY)).toEqual(clock);
  });

  it("falls back to the initial clock for bad data", () => {
    for (const bad of ["{not json", "null", "[]", '{"activeMs":"x"}', '{"activeMs":1}']) {
      expect(loadClock(memoryStorage({ [KEY]: bad }), KEY)).toEqual(initialClock());
    }
    const throwing = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
    };
    expect(loadClock(throwing, KEY)).toEqual(initialClock());
    expect(() => saveClock(throwing, KEY, initialClock())).not.toThrow();
  });
});
