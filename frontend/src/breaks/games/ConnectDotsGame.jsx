import { useState } from "react";
import { SIZE, SYMBOL_NAMES, initialState, isComplete, press } from "./connectDots";

const connected = (puzzle, state, i) => {
  const path = state.paths[i];
  return path.length > 1 && puzzle.pairs[i].ends.includes(path[0]) && puzzle.pairs[i].ends.includes(path[path.length - 1]);
};

export default function ConnectDotsGame({ puzzle, showSolution, locked, onSolved }) {
  const [state, setState] = useState(() => initialState(puzzle));
  const [message, setMessage] = useState("");
  const paths = showSolution ? puzzle.solution : state.paths;

  function pick(cell) {
    if (locked || showSolution) return;
    const next = press(puzzle, state, cell);
    if (next === state) return;
    setState(next);

    // Say what changed, since colour alone must never carry the information.
    const justConnected = puzzle.pairs.findIndex((_, i) => connected(puzzle, next, i) && !connected(puzzle, state, i));
    if (justConnected !== -1) setMessage(`Pair ${justConnected + 1} connected`);
    else if (next.active !== null && next.active !== state.active) {
      setMessage(`Drawing pair ${next.active + 1} (${SYMBOL_NAMES[next.active]})`);
    }

    if (isComplete(puzzle, next)) onSolved();
  }

  return (
    <div className="brk-game">
      <p className="brk-instruction">Join each pair of matching dots with a path.</p>
      <div className="brk-dots" role="group" aria-label="Connect the dots board">
        {Array.from({ length: SIZE * SIZE }, (_, cell) => {
          const endpointOf = puzzle.pairs.findIndex((p) => p.ends.includes(cell));
          const owner = paths.findIndex((p) => p.includes(cell));
          const pair = endpointOf !== -1 ? endpointOf : owner;
          const where = `Row ${Math.floor(cell / SIZE) + 1}, column ${(cell % SIZE) + 1}`;
          let label = `${where}, empty`;
          if (endpointOf !== -1) label = `${where}, dot ${SYMBOL_NAMES[endpointOf]}, pair ${endpointOf + 1}`;
          else if (owner !== -1) label = `${where}, path of pair ${owner + 1}`;
          const isActive = !showSolution && state.active !== null && pair === state.active;
          return (
            <button
              key={cell}
              type="button"
              className={`brk-dot-cell ${pair !== -1 ? `brk-pair-${pair}` : ""} ${endpointOf !== -1 ? "brk-dot-end" : ""} ${
                isActive ? "brk-dot-active" : ""
              }`}
              aria-disabled={locked || showSolution}
              onClick={() => pick(cell)}
              aria-label={label}
            >
              <span aria-hidden="true">{pair !== -1 ? puzzle.pairs[pair].symbol : ""}</span>
            </button>
          );
        })}
      </div>
      <p className="brk-feedback" aria-live="polite">
        {message}
      </p>
    </div>
  );
}
