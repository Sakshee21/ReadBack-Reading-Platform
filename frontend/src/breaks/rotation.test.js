import { describe, expect, it } from "vitest";
import { mulberry32 } from "./rng";
import { gameIds } from "./registry";
import { nextGameId } from "./rotation";

function memoryStorage(initial = {}) {
  const data = { ...initial };
  return {
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => {
      data[k] = v;
    },
  };
}

const IDS = ["a", "b", "c"];

describe("nextGameId", () => {
  it("plays every game before any repeat", () => {
    const storage = memoryStorage();
    const rand = mulberry32(3);
    const first = [0, 1, 2].map(() => nextGameId(IDS, storage, rand));
    const second = [0, 1, 2].map(() => nextGameId(IDS, storage, rand));
    expect([...first].sort()).toEqual(IDS);
    expect([...second].sort()).toEqual(IDS);
  });

  it("never repeats the same game back to back across refills", () => {
    const storage = memoryStorage();
    const rand = mulberry32(11);
    let prev = null;
    for (let i = 0; i < 30; i++) {
      const id = nextGameId(IDS, storage, rand);
      expect(id).not.toBe(prev);
      prev = id;
    }
  });

  it("always returns the only game when there is one", () => {
    const storage = memoryStorage();
    for (let i = 0; i < 5; i++) expect(nextGameId(["solo"], storage, mulberry32(1))).toBe("solo");
  });

  it("discards stored ids that are no longer registered", () => {
    const storage = memoryStorage({
      readback_break_rotation: JSON.stringify({ bag: ["old", "a"], last: null }),
    });
    const seen = [0, 1, 2, 3, 4, 5].map(() => nextGameId(IDS, storage, mulberry32(5)));
    expect(seen).not.toContain("old");
    expect(seen.every((id) => IDS.includes(id))).toBe(true);
  });

  it("recovers from corrupt or unavailable storage", () => {
    expect(IDS).toContain(
      nextGameId(IDS, memoryStorage({ readback_break_rotation: "{nope" }), mulberry32(1))
    );
    const throwing = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
    };
    expect(IDS).toContain(nextGameId(IDS, throwing, mulberry32(1)));
  });

  it("continues the same bag after a reload", () => {
    const storage = memoryStorage();
    const rand = mulberry32(9);
    const a = nextGameId(IDS, storage, rand);
    const b = nextGameId(IDS, storage, rand);
    const c = nextGameId(IDS, storage, rand);
    expect(new Set([a, b, c]).size).toBe(3);
  });

  it("plays all six registry games before any repeat", () => {
    const ids = gameIds();
    expect(ids).toHaveLength(6);
    const storage = memoryStorage();
    const rand = mulberry32(4);
    for (let round = 0; round < 2; round++) {
      const played = ids.map(() => nextGameId(ids, storage, rand));
      expect([...played].sort()).toEqual([...ids].sort());
    }
  });
});
