// @vitest-environment jsdom
// Drives the real hook, offer and shell with React to pin the collision and
// anti-immersion rules from the reading-breaks spec (sections 4, 5 and 9).
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const logged = [];
vi.mock("../api", () => ({ logEvent: (type, fields) => logged.push({ type, ...fields }) }));
vi.mock("./breakClock", async (importOriginal) => {
  const real = await importOriginal();
  return { ...real, evaluateBreak: vi.fn(real.evaluateBreak) };
});

import BreakOffer from "../components/BreakOffer";
import BreakShell from "../components/BreakShell";
import { evaluateBreak } from "./breakClock";
import { BREAK_AFTER_ACTIVE_MS, BREAK_GAME_CAP_MS } from "./constants";
import { GAMES, gameIds } from "./registry";
import { roundSeed } from "./rounds";
import { useBreakFlow } from "./useBreakFlow";

let api;
let resumed;
let randomSpy;

const oddGame = () => GAMES.find((g) => g.id === "odd_one_out");
// Stage 1 tests solve the odd-one-out grid, so pin the rotation to it and use
// an even seed (Math.random 0.5) which selects the grid variant.
function pinGame(id) {
  localStorage.setItem("readback_break_rotation", JSON.stringify({ bag: [id], last: null }));
}

function Harness({ enabled = true, celebrationActive = false, crash = false }) {
  const b = useBreakFlow({ enabled, celebrationActive, resume: () => (resumed += 1) });
  api = b;
  const game =
    crash && b.game
      ? {
          ...b.game,
          Component: () => {
            throw new Error("boom");
          },
        }
      : b.game;
  return (
    <div>
      <span data-testid="phase">{b.phase}</span>
      {b.phase === "offered" && <BreakOffer onAccept={b.accept} onDecline={b.decline} />}
      {(b.phase === "playing" || b.phase === "ended") && game && (
        <BreakShell
          game={game}
          puzzle={b.puzzle}
          seed={b.seed}
          rounds={b.rounds}
          onFinish={b.finish}
          onDone={b.done}
          onError={b.onGameError}
        />
      )}
    </div>
  );
}

const ctx = { bookId: 1, chapterId: 2, microSessionId: 3 };
function complete(over = {}) {
  let result;
  act(() => {
    result = api.onSessionComplete({
      activeMs: BREAK_AFTER_ACTIVE_MS,
      quizDue: false,
      finished: false,
      ctx,
      ...over,
    });
  });
  return result;
}
// Clicks the right answer for round `r` of the odd-one-out game started in this test.
function solveOddRound(r) {
  const seed = logged.find((e) => e.type === "break_game_start").seed;
  const game = oddGame();
  const puzzle = game.generate(roundSeed(seed, r));
  const answer = game.solve(puzzle);
  if (puzzle.kind === "next") {
    fireEvent.click(screen.getByRole("button", { name: new RegExp("^Option " + (answer + 1) + ":") }));
  } else {
    fireEvent.click(oddCells()[answer]);
  }
}
const phase = () => screen.getByTestId("phase").textContent;
const types = () => logged.map((e) => e.type);
const oddCells = () =>
  screen.getAllByRole("button").filter((b) => /filled|outline/.test(b.getAttribute("aria-label") || ""));

beforeEach(() => {
  logged.length = 0;
  resumed = 0;
  localStorage.clear();
  pinGame("odd_one_out");
  randomSpy = vi.spyOn(Math, "random").mockReturnValue(0.5);
  vi.useFakeTimers();
});
afterEach(() => {
  cleanup();
  randomSpy.mockRestore();
  vi.useRealTimers();
});

describe("break flow", () => {
  it("offers only after 10 active minutes and waits for the celebration", () => {
    const { rerender } = render(<Harness celebrationActive />);
    complete({ activeMs: BREAK_AFTER_ACTIVE_MS - 1 });
    expect(phase()).toBe("idle");
    complete({ activeMs: 1 });
    expect(phase()).toBe("due");
    expect(screen.queryByRole("dialog")).toBeNull();
    rerender(<Harness celebrationActive={false} />);
    expect(phase()).toBe("offered");
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(types()).toContain("break_offered");
  });

  it("decline resumes reading immediately and does not re-offer next session", () => {
    render(<Harness />);
    complete();
    fireEvent.click(screen.getByText("No thanks, keep reading"));
    expect(phase()).toBe("idle");
    expect(resumed).toBe(1);
    complete({ activeMs: 60_000 });
    expect(phase()).toBe("idle");
    expect(types()).toContain("break_declined");
  });

  it("accept, solve every puzzle, end card with one button, back to reading", () => {
    render(<Harness />);
    complete();
    fireEvent.click(screen.getByText("Yes, a short break"));
    expect(phase()).toBe("playing");
    const start = logged.find((e) => e.type === "break_game_start");
    const puzzle = oddGame().generate(start.seed);
    const cells = oddCells();
    expect(cells).toHaveLength(9);
    fireEvent.click(cells.find((_, i) => i !== puzzle.oddIndex));
    expect(screen.getByText("Not quite, try another")).toBeTruthy();
    expect(phase()).toBe("playing");

    for (let r = 0; r < 3; r++) {
      expect(screen.getByText("Puzzle " + (r + 1) + " of 3")).toBeTruthy();
      solveOddRound(r);
      if (r < 2) {
        expect(phase()).toBe("playing");
        fireEvent.click(screen.getByText("Next puzzle"));
      }
    }
    expect(phase()).toBe("ended");
    expect(screen.getByText("Back to reading")).toBeTruthy();
    expect(screen.queryByText("Show solution")).toBeNull();
    expect(screen.queryByText("Next puzzle")).toBeNull();
    expect(screen.queryByText(/play again|score/i)).toBeNull();
    fireEvent.click(screen.getByText("Back to reading"));
    expect(phase()).toBe("idle");
    expect(resumed).toBe(1);
    const end = logged.find((e) => e.type === "break_game_end");
    expect(end).toMatchObject({ outcome: "solved", rounds: 3, rounds_solved: 3 });
    expect(types()).toContain("break_back_to_reading");
  });

  it("show solution reveals the answer and moves on to the next puzzle", () => {
    render(<Harness />);
    complete();
    fireEvent.click(screen.getByText("Yes, a short break"));
    fireEvent.click(screen.getByText("Show solution"));
    expect(screen.getByText("This one")).toBeTruthy();
    expect(phase()).toBe("playing");
    expect(screen.queryByText("Show solution")).toBeNull();
    fireEvent.click(screen.getByText("Next puzzle"));
    expect(screen.getByText("Puzzle 2 of 3")).toBeTruthy();
    solveOddRound(1);
    fireEvent.click(screen.getByText("Next puzzle"));
    solveOddRound(2);
    expect(phase()).toBe("ended");
    expect(logged.find((e) => e.type === "break_game_end")).toMatchObject({
      outcome: "shown_solution",
      rounds: 3,
      rounds_solved: 2,
    });
  });

  it("a four-puzzle break runs four rounds", () => {
    randomSpy.mockReturnValue((2147483648 + 2) / 4294967296); // even seed, four rounds
    render(<Harness />);
    complete();
    fireEvent.click(screen.getByText("Yes, a short break"));
    for (let r = 0; r < 4; r++) {
      expect(screen.getByText("Puzzle " + (r + 1) + " of 4")).toBeTruthy();
      solveOddRound(r);
      if (r < 3) fireEvent.click(screen.getByText("Next puzzle"));
    }
    expect(phase()).toBe("ended");
    expect(logged.find((e) => e.type === "break_game_end")).toMatchObject({ rounds: 4, rounds_solved: 4 });
  });

  it("the longer games still run a single puzzle with no progress line", () => {
    pinGame("sliding_tile");
    render(<Harness />);
    complete();
    fireEvent.click(screen.getByText("Yes, a short break"));
    expect(screen.queryByText(/^Puzzle \d+ of \d+$/)).toBeNull();
    fireEvent.click(screen.getByText("Show solution"));
    expect(phase()).toBe("ended");
    expect(logged.find((e) => e.type === "break_game_end")).toMatchObject({ outcome: "shown_solution", rounds: 1 });
  });

  it("the 3 minute cap covers the whole break and records how far it got", () => {
    render(<Harness />);
    complete();
    fireEvent.click(screen.getByText("Yes, a short break"));
    solveOddRound(0);
    fireEvent.click(screen.getByText("Next puzzle"));
    act(() => vi.advanceTimersByTime(BREAK_GAME_CAP_MS));
    expect(phase()).toBe("ended");
    expect(logged.find((e) => e.type === "break_game_end")).toMatchObject({
      outcome: "time_cap",
      rounds: 3,
      rounds_solved: 1,
    });
  });

  it("skipping between puzzles leaves at once", () => {
    render(<Harness />);
    complete();
    fireEvent.click(screen.getByText("Yes, a short break"));
    solveOddRound(0);
    fireEvent.click(screen.getByText("Skip, back to reading"));
    expect(phase()).toBe("idle");
    expect(resumed).toBe(1);
    expect(logged.find((e) => e.type === "break_game_end")).toMatchObject({ outcome: "skipped", rounds_solved: 1 });
  });

  it("a later puzzle that cannot be built hands the reader back to reading", () => {
    const game = oddGame();
    const original = game.generate;
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      render(<Harness />);
      complete();
      fireEvent.click(screen.getByText("Yes, a short break"));
      solveOddRound(0);
      game.generate = () => {
        throw new Error("bad second puzzle");
      };
      fireEvent.click(screen.getByText("Next puzzle"));
      expect(phase()).toBe("idle");
      expect(resumed).toBe(1);
      expect(types()).toContain("break_game_error");
    } finally {
      game.generate = original;
      spy.mockRestore();
    }
  });

  it("skip button and Escape return to reading with no end card", () => {
    render(<Harness />);
    complete();
    fireEvent.click(screen.getByText("Yes, a short break"));
    fireEvent.click(screen.getByText("Skip, back to reading"));
    expect(phase()).toBe("idle");
    expect(resumed).toBe(1);
    expect(logged.filter((e) => e.type === "break_game_end")).toHaveLength(1);

    complete({ activeMs: BREAK_AFTER_ACTIVE_MS });
    fireEvent.click(screen.getByText("Yes, a short break"));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(phase()).toBe("idle");
    expect(resumed).toBe(2);
  });

  it("locks at the 3 minute cap and shows the time-cap end card", () => {
    render(<Harness />);
    complete();
    fireEvent.click(screen.getByText("Yes, a short break"));
    act(() => vi.advanceTimersByTime(BREAK_GAME_CAP_MS));
    expect(phase()).toBe("ended");
    expect(screen.getByText(/Time for a break from the break/)).toBeTruthy();
    expect(oddCells().every((b) => b.disabled)).toBe(true);
    expect(logged.find((e) => e.type === "break_game_end").outcome).toBe("time_cap");
    expect(logged.filter((e) => e.type === "break_game_end")).toHaveLength(1);
  });

  it("defers when a quiz is due, then offers at the next boundary", () => {
    render(<Harness />);
    complete({ quizDue: true });
    expect(phase()).toBe("idle");
    expect(logged.find((e) => e.type === "break_deferred").reason).toBe("quiz_due");
    complete({ activeMs: 1000 });
    expect(phase()).toBe("offered");
  });

  it("never offers when disabled or the book is finished", () => {
    const { unmount } = render(<Harness enabled={false} />);
    complete();
    expect(phase()).toBe("idle");
    unmount();
    cleanup();
    render(<Harness />);
    complete({ finished: true });
    expect(phase()).toBe("idle");
  });

  it("caps offers at three per day", () => {
    render(<Harness />);
    for (let i = 0; i < 3; i++) {
      complete();
      fireEvent.click(screen.getByText("No thanks, keep reading"));
    }
    complete();
    expect(phase()).toBe("idle");
  });

  it("a crashing game ends the break as skipped and returns to reading", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(<Harness crash />);
    complete();
    fireEvent.click(screen.getByText("Yes, a short break"));
    expect(phase()).toBe("idle");
    expect(resumed).toBe(1);
    expect(types()).toContain("break_game_error");
    spy.mockRestore();
  });

  it("every break event carries active_ms_since_last_break", () => {
    render(<Harness />);
    complete();
    fireEvent.click(screen.getByText("Yes, a short break"));
    fireEvent.click(screen.getByText("Skip, back to reading"));
    const breakEvents = logged.filter((e) => e.type.startsWith("break_"));
    expect(breakEvents.length).toBeGreaterThanOrEqual(5);
    for (const e of breakEvents) expect(e.active_ms_since_last_break).toBeTypeOf("number");
  });
});

describe("review fixes", () => {
  it("the break overlay sits above every other overlay in global.css", () => {
    const zOf = (css) => [...css.matchAll(/z-index:\s*(\d+)/g)].map((m) => Number(m[1]));
    const global = readFileSync(resolve(process.cwd(), "src/styles/global.css"), "utf8");
    const breaks = readFileSync(resolve(process.cwd(), "src/styles/breaks.css"), "utf8");
    expect(Math.min(...zOf(breaks))).toBeGreaterThan(Math.max(...zOf(global)));
  });

  it("cancelDue drops a pending break but keeps the clock for the next boundary", () => {
    const { rerender } = render(<Harness celebrationActive />);
    complete();
    expect(phase()).toBe("due");
    act(() => api.cancelDue());
    expect(phase()).toBe("idle");
    rerender(<Harness celebrationActive={false} />);
    expect(phase()).toBe("idle");
    complete({ activeMs: 1000 });
    expect(phase()).toBe("offered");
  });

  it("Escape declines the offer", () => {
    const onDecline = vi.fn();
    render(<BreakOffer onAccept={vi.fn()} onDecline={onDecline} />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onDecline).toHaveBeenCalledTimes(1);
  });

  it("Tab stays inside the offer dialog", () => {
    render(<BreakOffer onAccept={vi.fn()} onDecline={vi.fn()} />);
    screen.getByText("No thanks, keep reading").focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(screen.getByText("Yes, a short break"));
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(screen.getByText("No thanks, keep reading"));
  });

  it("the end card takes focus and Escape on it goes back to reading", () => {
    const onDone = vi.fn();
    const puzzle = oddGame().generate(2);
    render(<BreakShell game={oddGame()} puzzle={puzzle} onFinish={vi.fn()} onDone={onDone} onError={vi.fn()} />);
    fireEvent.click(oddCells()[puzzle.oddIndex]);
    expect(document.activeElement).toBe(screen.getByText("Back to reading"));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("a puzzle generator that throws does not take down the reader", () => {
    const game = oddGame();
    const original = game.generate;
    game.generate = () => {
      throw new Error("bad generator");
    };
    try {
      render(<Harness />);
      complete();
      fireEvent.click(screen.getByText("Yes, a short break"));
      expect(phase()).toBe("idle");
      expect(resumed).toBe(1);
      expect(types()).toContain("break_game_error");
    } finally {
      game.generate = original;
    }
  });

  it("an empty registry cannot strand the reader", () => {
    const saved = GAMES.splice(0);
    try {
      render(<Harness />);
      complete();
      fireEvent.click(screen.getByText("Yes, a short break"));
      expect(phase()).toBe("idle");
      expect(resumed).toBe(1);
    } finally {
      GAMES.push(...saved);
    }
  });

  it("a failure inside the clock logic never throws into the reader", () => {
    render(<Harness />);
    evaluateBreak.mockImplementationOnce(() => {
      throw new Error("clock bug");
    });
    let result;
    expect(() => {
      result = complete();
    }).not.toThrow();
    expect(result).toBe(false);
    expect(phase()).toBe("idle");
  });

  it("the first three breaks are three different games", () => {
    randomSpy.mockRestore();
    localStorage.clear();
    randomSpy = vi.spyOn(Math, "random");
    render(<Harness />);
    for (let i = 0; i < 3; i++) {
      complete();
      fireEvent.click(screen.getByText("Yes, a short break"));
      fireEvent.click(screen.getByText("Skip, back to reading"));
    }
    const played = logged.filter((e) => e.type === "break_game_start").map((e) => e.game_id);
    expect(played).toHaveLength(3);
    expect(new Set(played).size).toBe(3);
    for (const id of played) expect(gameIds()).toContain(id);
  });
});

describe("deferred minors: engine and shell", () => {
  const THRESH = BREAK_AFTER_ACTIVE_MS;

  it("a double click on Decline or Accept acts once", () => {
    render(<Harness />);
    complete();
    act(() => {
      api.decline();
      api.decline();
    });
    expect(resumed).toBe(1);
    expect(types().filter((t) => t === "break_declined")).toHaveLength(1);

    complete({ activeMs: THRESH });
    act(() => {
      api.accept();
      api.accept();
    });
    expect(types().filter((t) => t === "break_accepted")).toHaveLength(1);
    expect(types().filter((t) => t === "break_game_start")).toHaveLength(1);
  });

  it("two tabs share the clock, so the daily cap holds across them", () => {
    const apis = {};
    function Tab({ id }) {
      apis[id] = useBreakFlow({ enabled: true, celebrationActive: false, resume: () => {} });
      return null;
    }
    render(
      <>
        <Tab id="a" />
        <Tab id="b" />
      </>
    );
    for (let i = 0; i < 4; i++) {
      for (const id of ["a", "b"]) {
        act(() => {
          apis[id].onSessionComplete({ activeMs: THRESH, quizDue: false, finished: false, ctx });
        });
        if (apis[id].phase === "offered") act(() => apis[id].decline());
      }
    }
    expect(types().filter((t) => t === "break_offered")).toHaveLength(3);
  });

  it("time spent on a quiz does not erase a deferred break", () => {
    localStorage.setItem(
      "readback_break_clock",
      JSON.stringify({
        activeMs: THRESH + 1,
        lastSessionEndAt: Date.now() - 10 * 60 * 1000,
        offersToday: 0,
        offersDay: null,
      })
    );
    render(<Harness />);
    act(() => api.onQuizDone());
    act(() => api.onSessionStart());
    expect(complete({ activeMs: 0 })).toBe(true);
  });

  it("the 3 minute cap counts from when the game started, even after a remount", () => {
    const onFinish = vi.fn();
    const startedAt = Date.now() - (BREAK_GAME_CAP_MS - 1000);
    render(
      <BreakShell game={oddGame()} puzzle={oddGame().generate(2)} startedAt={startedAt} onFinish={onFinish} onDone={vi.fn()} onError={vi.fn()} />
    );
    act(() => vi.advanceTimersByTime(900));
    expect(onFinish).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(200));
    expect(onFinish).toHaveBeenCalledWith("time_cap", expect.any(Number), expect.any(Object));
  });

  it("the cap is enforced when the tab wakes up after a sleep", () => {
    const onFinish = vi.fn();
    render(<BreakShell game={oddGame()} puzzle={oddGame().generate(2)} onFinish={onFinish} onDone={vi.fn()} onError={vi.fn()} />);
    vi.setSystemTime(Date.now() + BREAK_GAME_CAP_MS + 1);
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(onFinish).toHaveBeenCalledWith("time_cap", expect.any(Number), expect.any(Object));
  });

  it("closing the tab mid-game logs how long it ran", () => {
    render(<Harness />);
    complete();
    fireEvent.click(screen.getByText("Yes, a short break"));
    act(() => vi.advanceTimersByTime(5000));
    act(() => {
      window.dispatchEvent(new Event("pagehide"));
    });
    const end = logged.filter((e) => e.type === "break_game_end").pop();
    expect(end.outcome).toBe("skipped");
    expect(end.duration_ms).toBeGreaterThanOrEqual(5000);
  });

  it("opening a word game does not pop the mobile keyboard", () => {
    pinGame("word_play");
    render(<Harness />);
    complete();
    fireEvent.click(screen.getByText("Yes, a short break"));
    expect(document.activeElement.tagName).not.toBe("INPUT");
    expect(screen.getByRole("dialog").contains(document.activeElement)).toBe(true);
  });

  it("Shift+Tab from the dialog itself stays inside it", () => {
    render(<Harness />);
    complete();
    fireEvent.click(screen.getByText("Yes, a short break"));
    const notPrevented = fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(notPrevented).toBe(false);
    expect(screen.getByRole("dialog").contains(document.activeElement)).toBe(true);
  });
});

describe("flash review: multi-puzzle breaks", () => {
  it("moves focus into the dialog and announces the position after Next puzzle", () => {
    render(<Harness />);
    complete();
    fireEvent.click(screen.getByText("Yes, a short break"));
    solveOddRound(0);
    fireEvent.click(screen.getByText("Next puzzle"));
    expect(document.activeElement).toBe(screen.getByRole("dialog"));
    expect(screen.getByText("Puzzle 2 of 3").getAttribute("aria-live")).toBe("polite");
  });

  it("a double click on Next puzzle advances once", () => {
    render(<Harness />);
    complete();
    fireEvent.click(screen.getByText("Yes, a short break"));
    solveOddRound(0);
    const next = screen.getByText("Next puzzle");
    act(() => {
      next.click();
      next.click();
    });
    expect(screen.getByText("Puzzle 2 of 3")).toBeTruthy();
  });

  it("the cap fires while waiting between puzzles and keeps the count", () => {
    render(<Harness />);
    complete();
    fireEvent.click(screen.getByText("Yes, a short break"));
    solveOddRound(0);
    expect(screen.getByText("Next puzzle")).toBeTruthy();
    act(() => vi.advanceTimersByTime(BREAK_GAME_CAP_MS));
    expect(phase()).toBe("ended");
    expect(logged.find((e) => e.type === "break_game_end")).toMatchObject({ outcome: "time_cap", rounds_solved: 1 });
  });

  it("a solve reported after Show solution is ignored", () => {
    const calls = [];
    function Fake({ onSolved }) {
      calls.push(onSolved);
      return <button onClick={onSolved}>fake solve</button>;
    }
    const fake = { id: "fake", generate: () => ({}), solve: () => 0, Component: Fake };
    const onFinish = vi.fn();
    render(<BreakShell game={fake} puzzle={{}} seed={2} rounds={3} onFinish={onFinish} onDone={vi.fn()} onError={vi.fn()} />);
    fireEvent.click(screen.getByText("Show solution"));
    fireEvent.click(screen.getByText("fake solve")); // the game reports a solve after the reveal
    fireEvent.click(screen.getByText("Next puzzle"));
    fireEvent.click(screen.getByText("fake solve"));
    fireEvent.click(screen.getByText("Next puzzle"));
    fireEvent.click(screen.getByText("fake solve"));
    expect(onFinish).toHaveBeenCalledTimes(1);
    expect(onFinish.mock.calls[0][0]).toBe("shown_solution");
    expect(onFinish.mock.calls[0][2]).toMatchObject({ rounds: 3, rounds_solved: 2 });
  });

  it("closing the tab mid-break also logs how many puzzles the break had", () => {
    render(<Harness />);
    complete();
    fireEvent.click(screen.getByText("Yes, a short break"));
    act(() => {
      window.dispatchEvent(new Event("pagehide"));
    });
    const end = logged.filter((e) => e.type === "break_game_end").pop();
    expect(end).toMatchObject({ outcome: "skipped", rounds: 3 });
  });

  it("word play switches from a ladder to an anagram between puzzles", () => {
    pinGame("word_play");
    render(<Harness />);
    complete();
    fireEvent.click(screen.getByText("Yes, a short break"));
    const seed = logged.find((e) => e.type === "break_game_start").seed;
    const game = GAMES.find((g) => g.id === "word_play");
    const first = game.generate(roundSeed(seed, 0));
    expect(first.kind).toBe("ladder");
    for (const word of first.path.slice(1)) {
      fireEvent.change(screen.getByLabelText("Next word"), { target: { value: word } });
      fireEvent.click(screen.getByText("Add word"));
    }
    fireEvent.click(screen.getByText("Next puzzle"));
    expect(game.generate(roundSeed(seed, 1)).kind).toBe("anagram");
    expect(screen.getByLabelText("Your answer")).toBeTruthy();
    expect(screen.queryByLabelText("Next word")).toBeNull();
  });
});
