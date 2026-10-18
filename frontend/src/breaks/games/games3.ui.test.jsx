// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import BreakShell from "../../components/BreakShell";
import { GAMES } from "../registry";
import ConnectDotsGame from "./ConnectDotsGame";
import MiniSudokuGame from "./MiniSudokuGame";
import WordPlayGame from "./WordPlayGame";
import { generate as dotsGenerate, SYMBOL_NAMES } from "./connectDots";
import { generate as sudokuGenerate } from "./miniSudoku";
import { generate as wordGenerate, shortestPath } from "./wordPlay";

afterEach(cleanup);

const props = (over = {}) => ({ showSolution: false, locked: false, onSolved: vi.fn(), ...over });

describe("ConnectDotsGame", () => {
  const puzzle = dotsGenerate(1);
  const cell = (idx) =>
    screen.getByRole("button", { name: new RegExp(`^Row ${Math.floor(idx / 5) + 1}, column ${(idx % 5) + 1},`) });

  it("is solved, once, by drawing every pair", () => {
    const onSolved = vi.fn();
    render(<ConnectDotsGame puzzle={puzzle} {...props({ onSolved })} />);
    puzzle.solution.forEach((path) => {
      expect(onSolved).not.toHaveBeenCalled();
      path.forEach((idx) => fireEvent.click(cell(idx)));
    });
    expect(onSolved).toHaveBeenCalledTimes(1);
  });

  it("ignores a cell that is not next to the path", () => {
    render(<ConnectDotsGame puzzle={puzzle} {...props()} />);
    const start = puzzle.pairs[0].ends[0];
    fireEvent.click(cell(start));
    const far = [...Array(25).keys()].find(
      (i) => Math.abs(i - start) > 6 && puzzle.pairs.every((p) => !p.ends.includes(i))
    );
    fireEvent.click(cell(far));
    expect(cell(far).getAttribute("aria-label")).toMatch(/empty$/);
  });

  it("says which pair is being drawn and when one is connected", () => {
    render(<ConnectDotsGame puzzle={puzzle} {...props()} />);
    fireEvent.click(cell(puzzle.pairs[1].ends[0]));
    expect(screen.getByText(/Drawing pair 2/)).toBeTruthy();
    puzzle.solution[0].forEach((idx) => fireEvent.click(cell(idx)));
    expect(screen.getByText("Pair 1 connected")).toBeTruthy();
  });

  it("labels endpoints with the symbol name and pair number, not only colour", () => {
    render(<ConnectDotsGame puzzle={puzzle} {...props()} />);
    puzzle.pairs.forEach((pair, i) => {
      const label = cell(pair.ends[0]).getAttribute("aria-label");
      expect(label).toContain(SYMBOL_NAMES[i]);
      expect(label).toContain(`pair ${i + 1}`);
    });
  });

  it("is inert when locked and draws the solution when asked", () => {
    const onSolved = vi.fn();
    const second = puzzle.solution[0][1];
    const { rerender } = render(<ConnectDotsGame puzzle={puzzle} {...props({ locked: true, onSolved })} />);
    fireEvent.click(cell(puzzle.pairs[0].ends[0]));
    fireEvent.click(cell(second));
    expect(cell(second).getAttribute("aria-label")).toMatch(/empty$/);

    rerender(<ConnectDotsGame puzzle={puzzle} {...props({ showSolution: true, onSolved })} />);
    expect(cell(second).getAttribute("aria-label")).toMatch(/path of pair 1/);
    const free = [...Array(25).keys()].find((i) => cell(i).getAttribute("aria-label").endsWith("empty"));
    fireEvent.click(cell(free));
    expect(cell(free).getAttribute("aria-label")).toMatch(/empty$/);
    expect(onSolved).not.toHaveBeenCalled();
  });
});

describe("MiniSudokuGame", () => {
  const puzzle = sudokuGenerate(2);
  const cell = (idx) =>
    screen.getByRole("button", { name: new RegExp(`^Row ${Math.floor(idx / 4) + 1}, column ${(idx % 4) + 1},`) });
  const pad = (n) => screen.getByRole("button", { name: `Enter ${n}` });
  const freeCells = puzzle.givens.map((v, i) => (v === 0 ? i : -1)).filter((i) => i >= 0);

  it("fills in the solution and calls onSolved exactly once", () => {
    const onSolved = vi.fn();
    render(<MiniSudokuGame puzzle={puzzle} {...props({ onSolved })} />);
    freeCells.forEach((idx, n) => {
      expect(onSolved).not.toHaveBeenCalled();
      fireEvent.click(cell(idx));
      fireEvent.click(pad(puzzle.solution[idx]));
      expect(onSolved).toHaveBeenCalledTimes(n === freeCells.length - 1 ? 1 : 0);
    });
  });

  it("does not let givens be edited", () => {
    render(<MiniSudokuGame puzzle={puzzle} {...props()} />);
    const g = puzzle.givens.findIndex((v) => v !== 0);
    const before = cell(g).getAttribute("aria-label");
    expect(before).toContain("given");
    fireEvent.click(cell(g));
    fireEvent.click(pad(puzzle.givens[g] === 1 ? 2 : 1));
    expect(cell(g).getAttribute("aria-label")).toBe(before);
  });

  it("marks a conflict with a symbol and in the label", () => {
    render(<MiniSudokuGame puzzle={puzzle} {...props()} />);
    let pick = null;
    for (const f of freeCells) {
      const row = Math.floor(f / 4);
      const g = [0, 1, 2, 3].map((c) => row * 4 + c).find((i) => puzzle.givens[i] !== 0);
      if (g !== undefined) {
        pick = { f, digit: puzzle.givens[g] };
        break;
      }
    }
    expect(pick).not.toBeNull();
    fireEvent.click(cell(pick.f));
    fireEvent.click(pad(pick.digit));
    expect(cell(pick.f).getAttribute("aria-label")).toContain("conflict");
    expect(screen.getAllByText("!").length).toBeGreaterThanOrEqual(1);
  });

  it("accepts digits from the keyboard", () => {
    render(<MiniSudokuGame puzzle={puzzle} {...props()} />);
    const f = freeCells[0];
    fireEvent.keyDown(cell(f), { key: "3" });
    expect(cell(f).getAttribute("aria-label")).toContain("value 3");
    fireEvent.keyDown(cell(f), { key: "Backspace" });
    expect(cell(f).getAttribute("aria-label")).toContain("empty");
  });

  it("writes to the cell that has keyboard focus, not a stale selection", () => {
    render(<MiniSudokuGame puzzle={puzzle} {...props()} />);
    const [a, b] = freeCells;
    fireEvent.click(cell(a));
    act(() => cell(b).focus());
    fireEvent.click(pad(2));
    expect(cell(b).getAttribute("aria-label")).toContain("value 2");
    expect(cell(a).getAttribute("aria-label")).toContain("empty");
  });

  it("ignores digits typed with Ctrl, Alt or Meta", () => {
    render(<MiniSudokuGame puzzle={puzzle} {...props()} />);
    const f = freeCells[0];
    for (const mod of [{ ctrlKey: true }, { altKey: true }, { metaKey: true }]) {
      fireEvent.keyDown(cell(f), { key: "3", ...mod });
    }
    expect(cell(f).getAttribute("aria-label")).toContain("empty");
  });

  it("moves between cells with the arrow keys and stops at the edges", () => {
    render(<MiniSudokuGame puzzle={puzzle} {...props()} />);
    cell(5).focus();
    fireEvent.keyDown(cell(5), { key: "ArrowRight" });
    expect(document.activeElement).toBe(cell(6));
    fireEvent.keyDown(cell(6), { key: "ArrowDown" });
    expect(document.activeElement).toBe(cell(10));
    fireEvent.keyDown(cell(10), { key: "ArrowLeft" });
    expect(document.activeElement).toBe(cell(9));
    fireEvent.keyDown(cell(9), { key: "ArrowUp" });
    expect(document.activeElement).toBe(cell(5));
    cell(4).focus();
    fireEvent.keyDown(cell(4), { key: "ArrowLeft" });
    expect(document.activeElement).toBe(cell(4));
    cell(1).focus();
    fireEvent.keyDown(cell(1), { key: "ArrowUp" });
    expect(document.activeElement).toBe(cell(1));
  });

  it("announces what was entered", () => {
    render(<MiniSudokuGame puzzle={puzzle} {...props()} />);
    const f = freeCells[0];
    fireEvent.keyDown(cell(f), { key: "3" });
    expect(screen.getByText(/set to 3/i)).toBeTruthy();
    fireEvent.keyDown(cell(f), { key: "Backspace" });
    expect(screen.getByText(/cleared/i)).toBeTruthy();
  });

  it("is inert when locked and shows the solution when asked", () => {
    const onSolved = vi.fn();
    const f = freeCells[0];
    const { rerender } = render(<MiniSudokuGame puzzle={puzzle} {...props({ locked: true, onSolved })} />);
    fireEvent.click(cell(f));
    fireEvent.click(pad(2));
    fireEvent.keyDown(cell(f), { key: "3" });
    expect(cell(f).getAttribute("aria-label")).toContain("empty");
    rerender(<MiniSudokuGame puzzle={puzzle} {...props({ showSolution: true, onSolved })} />);
    expect(cell(f).getAttribute("aria-label")).toContain(`value ${puzzle.solution[f]}`);
    const wrong = puzzle.solution[f] === 1 ? 2 : 1;
    fireEvent.click(cell(f));
    fireEvent.click(pad(wrong));
    fireEvent.keyDown(cell(f), { key: String(wrong) });
    expect(cell(f).getAttribute("aria-label")).toContain(`value ${puzzle.solution[f]}`);
    expect(onSolved).not.toHaveBeenCalled();
  });
});

describe("WordPlayGame, ladder", () => {
  const puzzle = wordGenerate(0);
  const input = () => screen.getByLabelText("Next word");
  const submit = (text) => {
    fireEvent.change(input(), { target: { value: text } });
    fireEvent.click(screen.getByText("Add word"));
  };

  it("accepts the path word by word and solves once", () => {
    const onSolved = vi.fn();
    render(<WordPlayGame puzzle={puzzle} {...props({ onSolved })} />);
    puzzle.path.slice(1).forEach((w, i, rest) => {
      expect(onSolved).not.toHaveBeenCalled();
      submit(w);
      if (i < rest.length - 1) expect(screen.getAllByText(new RegExp(`^${w}$`, "i")).length).toBeGreaterThan(0);
    });
    expect(onSolved).toHaveBeenCalledTimes(1);
  });

  it("explains a rejected word gently", () => {
    render(<WordPlayGame puzzle={puzzle} {...props()} />);
    submit("abc");
    expect(screen.getByText("Use 4 letters")).toBeTruthy();
    submit("xxxx");
    expect(screen.getByText("Not a word we know")).toBeTruthy();
    submit(puzzle.target === "zero" ? "zone" : "zero");
    expect(screen.getByText("Change exactly one letter")).toBeTruthy();
    submit(puzzle.path[1]);
    submit(puzzle.start);
    expect(screen.getByText("Already used")).toBeTruthy();
  });

  it("shows the next word as a hint", () => {
    render(<WordPlayGame puzzle={puzzle} {...props()} />);
    fireEvent.click(screen.getByText("Hint"));
    expect(screen.getByText(new RegExp(puzzle.path[1], "i"), { selector: "[aria-live]" })).toBeTruthy();
  });

  it("lets the player undo the last word", () => {
    render(<WordPlayGame puzzle={puzzle} {...props()} />);
    const undo = screen.getByText("Undo last word");
    expect(undo.disabled).toBe(true);
    submit(puzzle.path[1]);
    expect(undo.disabled).toBe(false);
    fireEvent.click(undo);
    expect(screen.queryAllByText(new RegExp(`^${puzzle.path[1]}$`, "i"), { selector: "li" })).toHaveLength(0);
    expect(undo.disabled).toBe(true);
  });

  it("hints away from a dead end instead of back at a used word", () => {
    // bold is a legal first step on cold -> hard whose natural hint is "cold"
    const coldHard = { kind: "ladder", start: "cold", target: "hard", path: shortestPath("cold", "hard") };
    render(<WordPlayGame puzzle={coldHard} {...props()} />);
    submit("bold");
    fireEvent.click(screen.getByText("Hint"));
    const live = screen.getByText(/^(Try:|No way forward)/, { selector: "[aria-live]" });
    expect(live.textContent).not.toMatch(/cold/i);
  });

  it("does not cut off a pasted word before it is trimmed, and turns autocorrect off", () => {
    const onSolved = vi.fn();
    render(<WordPlayGame puzzle={puzzle} {...props({ onSolved })} />);
    expect(input().getAttribute("maxlength")).toBeNull();
    expect(input().getAttribute("autocorrect")).toBe("off");
    submit("  " + puzzle.path[1].toUpperCase() + "  ");
    expect(screen.queryByText("Use 4 letters")).toBeNull();
    expect(screen.getAllByText(new RegExp("^" + puzzle.path[1] + "$", "i")).length).toBeGreaterThan(0);
  });

  it("re-announces a repeated hint", () => {
    render(<WordPlayGame puzzle={puzzle} {...props()} />);
    const live = () => screen.getByText(/^Try:/, { selector: "[aria-live]" });
    fireEvent.click(screen.getByText("Hint"));
    const first = live().textContent;
    fireEvent.click(screen.getByText("Hint"));
    expect(live().textContent).not.toBe(first);
  });

  it("is inert when locked and shows the whole path as the solution", () => {
    const { rerender } = render(<WordPlayGame puzzle={puzzle} {...props({ locked: true })} />);
    expect(input().disabled).toBe(true);
    rerender(<WordPlayGame puzzle={puzzle} {...props({ showSolution: true })} />);
    for (const w of puzzle.path) expect(screen.getAllByText(new RegExp(`^${w}$`, "i")).length).toBeGreaterThan(0);
  });
});

describe("WordPlayGame, anagram", () => {
  const puzzle = wordGenerate(1);
  const input = () => screen.getByLabelText("Your answer");

  it("rejects a wrong answer and accepts the right one once", () => {
    const onSolved = vi.fn();
    render(<WordPlayGame puzzle={puzzle} {...props({ onSolved })} />);
    fireEvent.change(input(), { target: { value: "wrong" } });
    fireEvent.click(screen.getByText("Check"));
    expect(screen.getByText("Not quite, try another")).toBeTruthy();
    expect(onSolved).not.toHaveBeenCalled();
    fireEvent.change(input(), { target: { value: ` ${puzzle.word.toUpperCase()} ` } });
    fireEvent.click(screen.getByText("Check"));
    expect(onSolved).toHaveBeenCalledTimes(1);
  });

  it("hints the first letter", () => {
    render(<WordPlayGame puzzle={puzzle} {...props()} />);
    fireEvent.click(screen.getByText("Hint"));
    expect(screen.getByText(`Starts with ${puzzle.word[0]}`)).toBeTruthy();
  });

  it("is inert when locked and reveals the word as the solution", () => {
    const { rerender } = render(<WordPlayGame puzzle={puzzle} {...props({ locked: true })} />);
    expect(input().disabled).toBe(true);
    rerender(<WordPlayGame puzzle={puzzle} {...props({ showSolution: true })} />);
    expect(screen.getAllByText(new RegExp(puzzle.word, "i")).length).toBeGreaterThan(0);
  });
});

describe("typing inside a game", () => {
  it("lets Escape from the word box reach the shell", () => {
    const game = GAMES.find((g) => g.id === "word_play");
    const onDone = vi.fn();
    render(
      <BreakShell
        game={game}
        puzzle={wordGenerate(0)}
        onFinish={vi.fn()}
        onDone={onDone}
        onError={vi.fn()}
      />
    );
    const box = screen.getByLabelText("Next word");
    box.focus();
    fireEvent.keyDown(box, { key: "a" });
    expect(onDone).not.toHaveBeenCalled();
    fireEvent.keyDown(box, { key: "Escape" });
    expect(onDone).toHaveBeenCalledTimes(1);
  });
});

describe("focus trap after the break ends", () => {
  it("keeps Shift+Tab inside the dialog when the word box is disabled", () => {
    const game = GAMES.find((g) => g.id === "word_play");
    render(
      <BreakShell game={game} puzzle={wordGenerate(0)} onFinish={vi.fn()} onDone={vi.fn()} onError={vi.fn()} />
    );
    fireEvent.click(screen.getByText("Show solution"));
    const back = screen.getByText("Back to reading");
    expect(document.activeElement).toBe(back);
    const notPrevented = fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(notPrevented).toBe(false); // the shell handled it, so focus cannot leave
  });
});
