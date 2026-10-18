// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MatchingCardsGame from "./MatchingCardsGame";
import OddOneOutGame from "./OddOneOutGame";
import SlidingTileGame from "./SlidingTileGame";
import { generate as patternGenerate, solve as patternSolve } from "./pattern";

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

// Cards 0/1 = a, 2/3 = b, 4/5 = c, 6/7 = d, 8/9 = e, 10/11 = f
const MATCH_PUZZLE = {
  cards: ["a", "b", "c", "d", "e", "f"].flatMap((s) => [s, s]).map((s) => ({ symbol: s, name: `sym ${s}` })),
};
const card = (n) => screen.getByRole("button", { name: new RegExp(`^Card ${n},`) });
const faceDown = (n) => card(n).getAttribute("aria-label") === `Card ${n}, face down`;

function props(over = {}) {
  return { showSolution: false, locked: false, onSolved: vi.fn(), ...over };
}

describe("MatchingCardsGame", () => {
  it("keeps a matched pair up and flips a mismatch back after 800 ms", () => {
    render(<MatchingCardsGame puzzle={MATCH_PUZZLE} {...props()} />);
    fireEvent.click(card(1));
    fireEvent.click(card(2)); // a, a
    expect(faceDown(1)).toBe(false);
    expect(faceDown(2)).toBe(false);

    fireEvent.click(card(3));
    fireEvent.click(card(5)); // b, c  -> mismatch
    expect(faceDown(3)).toBe(false);
    expect(faceDown(5)).toBe(false);
    act(() => vi.advanceTimersByTime(800));
    expect(faceDown(3)).toBe(true);
    expect(faceDown(5)).toBe(true);
    expect(faceDown(1)).toBe(false); // the pair stays up
  });

  it("ignores a third card while a mismatch is showing", () => {
    render(<MatchingCardsGame puzzle={MATCH_PUZZLE} {...props()} />);
    fireEvent.click(card(1));
    fireEvent.click(card(3)); // mismatch
    fireEvent.click(card(7));
    expect(faceDown(7)).toBe(true);
  });

  it("calls onSolved exactly once, after the last pair", () => {
    const onSolved = vi.fn();
    render(<MatchingCardsGame puzzle={MATCH_PUZZLE} {...props({ onSolved })} />);
    for (let pair = 0; pair < 6; pair++) {
      expect(onSolved).not.toHaveBeenCalled();
      fireEvent.click(card(pair * 2 + 1));
      fireEvent.click(card(pair * 2 + 2));
    }
    expect(onSolved).toHaveBeenCalledTimes(1);
  });

  it("is inert once locked and leaves no timer running after unmount", () => {
    const { rerender, unmount } = render(<MatchingCardsGame puzzle={MATCH_PUZZLE} {...props()} />);
    fireEvent.click(card(1));
    fireEvent.click(card(3)); // mismatch pending: one timer is running
    expect(vi.getTimerCount()).toBe(1);
    rerender(<MatchingCardsGame puzzle={MATCH_PUZZLE} {...props({ locked: true })} />);
    expect(vi.getTimerCount()).toBe(0); // locking cancels it
    act(() => vi.advanceTimersByTime(800));
    expect(faceDown(1)).toBe(false); // frozen, nothing flipped back
    fireEvent.click(card(7));
    expect(faceDown(7)).toBe(true);

    rerender(<MatchingCardsGame puzzle={MATCH_PUZZLE} {...props()} />);
    expect(vi.getTimerCount()).toBe(1);
    unmount();
    expect(vi.getTimerCount()).toBe(0); // unmounting cancels it
  });

  it("marks matched cards and announces a match or a miss", () => {
    render(<MatchingCardsGame puzzle={MATCH_PUZZLE} {...props()} />);
    fireEvent.click(card(1));
    fireEvent.click(card(2));
    expect(card(1).getAttribute("aria-label")).toContain("matched");
    expect(card(2).getAttribute("aria-label")).toContain("matched");
    expect(screen.getByText("Match!")).toBeTruthy();
    fireEvent.click(card(3));
    expect(card(3).getAttribute("aria-label")).not.toContain("matched");
    fireEvent.click(card(5));
    expect(screen.getByText("No match, turning back")).toBeTruthy();
  });

  it("shows every card when the solution is requested", () => {
    render(<MatchingCardsGame puzzle={MATCH_PUZZLE} {...props({ showSolution: true })} />);
    for (let n = 1; n <= 12; n++) expect(faceDown(n)).toBe(false);
  });
});

const tile = (n) => screen.getByRole("button", { name: new RegExp(`^Tile ${n},`) });
const order = () =>
  Array.from(screen.getByRole("group", { name: "Sliding tiles" }).children)
    .map((el) => el.textContent.trim())
    .join(",");

describe("SlidingTileGame", () => {
  it("moves an adjacent tile and calls onSolved once when solved", () => {
    const onSolved = vi.fn();
    render(<SlidingTileGame puzzle={{ tiles: [1, 2, 3, 4, 5, 6, 7, 0, 8] }} {...props({ onSolved })} />);
    fireEvent.click(tile(8));
    expect(onSolved).toHaveBeenCalledTimes(1);
    expect(order()).toBe("1,2,3,4,5,6,7,8,");
  });

  it("does nothing for a tile that is not next to the blank", () => {
    const onSolved = vi.fn();
    render(<SlidingTileGame puzzle={{ tiles: [1, 2, 3, 4, 5, 6, 7, 0, 8] }} {...props({ onSolved })} />);
    fireEvent.click(tile(1));
    expect(order()).toBe("1,2,3,4,5,6,7,,8");
    expect(onSolved).not.toHaveBeenCalled();
  });

  it("labels tiles and the empty space with their row and column", () => {
    render(<SlidingTileGame puzzle={{ tiles: [1, 2, 3, 4, 5, 6, 7, 8, 0] }} {...props()} />);
    expect(tile(8).getAttribute("aria-label")).toBe("Tile 8, row 3, column 2");
    expect(screen.getByRole("img", { name: "Empty space, row 3, column 3" })).toBeTruthy();
  });

  it("calls onSolved only once even if the board is solved again", () => {
    const onSolved = vi.fn();
    render(<SlidingTileGame puzzle={{ tiles: [1, 2, 3, 4, 5, 6, 7, 0, 8] }} {...props({ onSolved })} />);
    fireEvent.click(tile(8)); // solved
    fireEvent.click(tile(8)); // 8 slides back out
    fireEvent.click(tile(8)); // and in again: solved a second time
    expect(onSolved).toHaveBeenCalledTimes(1);
  });

  it("keeps keyboard focus on the tile that was moved", () => {
    render(<SlidingTileGame puzzle={{ tiles: [1, 2, 3, 4, 5, 6, 7, 8, 0] }} {...props()} />);
    tile(8).focus();
    fireEvent.click(tile(8));
    expect(order()).toBe("1,2,3,4,5,6,7,,8");
    expect(document.activeElement).toBe(tile(8));
  });

  it("ignores input when locked and shows the solved board for the solution", () => {
    const onSolved = vi.fn();
    const puzzle = { tiles: [1, 2, 3, 4, 5, 6, 7, 0, 8] };
    const { rerender } = render(<SlidingTileGame puzzle={puzzle} {...props({ locked: true, onSolved })} />);
    fireEvent.click(tile(8));
    expect(order()).toBe("1,2,3,4,5,6,7,,8");
    expect(onSolved).not.toHaveBeenCalled();
    rerender(<SlidingTileGame puzzle={puzzle} {...props({ showSolution: true, onSolved })} />);
    expect(order()).toBe("1,2,3,4,5,6,7,8,");
  });
});

describe("OddOneOutGame, what-comes-next variant", () => {
  const puzzle = patternGenerate(1); // odd seed -> kind "next"
  const option = (n) => screen.getByRole("button", { name: new RegExp(`^Option ${n}:`) });

  it("renders the sequence with four options; the right pick solves, a wrong pick does not", () => {
    expect(puzzle.kind).toBe("next");
    const onSolved = vi.fn();
    render(<OddOneOutGame puzzle={puzzle} {...props({ onSolved })} />);
    const right = patternSolve(puzzle);
    const wrong = [0, 1, 2, 3].find((i) => i !== right);
    fireEvent.click(option(wrong + 1));
    expect(screen.getByText("Not quite, try another")).toBeTruthy();
    expect(onSolved).not.toHaveBeenCalled();
    fireEvent.click(option(right + 1));
    expect(onSolved).toHaveBeenCalledTimes(1);
  });

  it("describes the given shapes to assistive technology", () => {
    render(<OddOneOutGame puzzle={puzzle} {...props()} />);
    const label = screen.getByRole("img").getAttribute("aria-label");
    for (const c of puzzle.sequence) expect(label).toContain(`${c.fill} ${c.shape}`);
    expect(label).toMatch(/missing/i);
  });

  it("marks the answer when the solution is requested and disables options when locked", () => {
    const { rerender } = render(<OddOneOutGame puzzle={puzzle} {...props({ showSolution: true })} />);
    expect(screen.getByText("This one")).toBeTruthy();
    rerender(<OddOneOutGame puzzle={puzzle} {...props({ locked: true })} />);
    for (let n = 1; n <= 4; n++) expect(option(n).disabled).toBe(true);
  });
});
