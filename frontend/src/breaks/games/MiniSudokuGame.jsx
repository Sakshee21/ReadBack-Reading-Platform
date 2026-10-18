import { useRef, useState } from "react";
import { conflicts, isSolved, setCell } from "./miniSudoku";

const DIGITS = [1, 2, 3, 4];
const SIZE = 4;

// Arrow keys move within the board and stop at its edges.
const ARROWS = {
  ArrowLeft: (i) => (i % SIZE === 0 ? i : i - 1),
  ArrowRight: (i) => (i % SIZE === SIZE - 1 ? i : i + 1),
  ArrowUp: (i) => (i < SIZE ? i : i - SIZE),
  ArrowDown: (i) => (i >= SIZE * (SIZE - 1) ? i : i + SIZE),
};

export default function MiniSudokuGame({ puzzle, showSolution, locked, onSolved }) {
  const [grid, setGrid] = useState(puzzle.givens);
  const [selected, setSelected] = useState(null);
  const [message, setMessage] = useState("");
  const cellRefs = useRef([]);
  const shown = showSolution ? puzzle.solution : grid;
  const clashing = new Set(conflicts(shown));

  function write(index, value) {
    if (locked || showSolution || index === null) return;
    const next = setCell(puzzle, grid, index, value);
    if (next === grid) return;
    setGrid(next);
    const where = `Row ${Math.floor(index / SIZE) + 1}, column ${(index % SIZE) + 1}`;
    const clash = conflicts(next).includes(index);
    setMessage(value === 0 ? `${where} cleared` : `${where} set to ${value}${clash ? ", conflict" : ""}`);
    if (isSolved(next)) onSolved();
  }

  function onKeyDown(e, index) {
    if (e.ctrlKey || e.altKey || e.metaKey) return; // leave browser shortcuts alone
    if (ARROWS[e.key]) {
      e.preventDefault();
      cellRefs.current[ARROWS[e.key](index)]?.focus();
    } else if (/^[1-4]$/.test(e.key)) {
      e.preventDefault();
      write(index, Number(e.key));
    } else if (e.key === "Backspace" || e.key === "Delete" || e.key === "0") {
      e.preventDefault();
      write(index, 0);
    }
  }

  return (
    <div className="brk-game">
      <p className="brk-instruction">Each row, column and 2×2 box holds 1 to 4 once.</p>
      <div className="brk-sudoku" role="group" aria-label="Mini sudoku board">
        {shown.map((v, i) => {
          const given = puzzle.givens[i] !== 0;
          const bad = clashing.has(i);
          const where = `Row ${Math.floor(i / SIZE) + 1}, column ${(i % SIZE) + 1}`;
          const label = `${where}, ${v ? `value ${v}` : "empty"}${given ? ", given" : ""}${bad ? ", conflict" : ""}`;
          return (
            <button
              key={i}
              ref={(el) => {
                cellRefs.current[i] = el;
              }}
              type="button"
              className={`brk-sudoku-cell ${given ? "brk-given" : ""} ${bad ? "brk-conflict" : ""} ${
                selected === i ? "brk-selected" : ""
              } ${i % SIZE === 1 ? "brk-box-right" : ""} ${Math.floor(i / SIZE) === 1 ? "brk-box-bottom" : ""}`}
              aria-disabled={locked || showSolution || given}
              onClick={() => setSelected(i)}
              onFocus={() => setSelected(i)}
              onKeyDown={(e) => onKeyDown(e, i)}
              aria-label={label}
            >
              <span aria-hidden="true">{v || ""}</span>
              {bad && (
                <span className="brk-mark" aria-hidden="true">
                  !
                </span>
              )}
            </button>
          );
        })}
      </div>
      <div className="brk-pad" role="group" aria-label="Number pad">
        {DIGITS.map((n) => (
          <button key={n} type="button" className="btn-secondary" aria-label={`Enter ${n}`} onClick={() => write(selected, n)}>
            {n}
          </button>
        ))}
        <button type="button" className="btn-secondary" onClick={() => write(selected, 0)}>
          Clear
        </button>
      </div>
      <p className="brk-feedback" aria-live="polite">
        {message}
      </p>
    </div>
  );
}
