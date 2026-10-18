import { useState } from "react";
import { isSolved } from "./pattern";

function Glyph({ shape, fill }) {
  const common = {
    fill: fill === "filled" ? "currentColor" : "none",
    stroke: "currentColor",
    strokeWidth: 4,
    strokeLinejoin: "round",
  };
  return (
    <svg viewBox="0 0 48 48" width="44" height="44" aria-hidden="true">
      {shape === "circle" && <circle cx="24" cy="24" r="16" {...common} />}
      {shape === "square" && <rect x="9" y="9" width="30" height="30" {...common} />}
      {shape === "triangle" && <polygon points="24,7 41,39 7,39" {...common} />}
      {shape === "diamond" && <polygon points="24,6 42,24 24,42 6,24" {...common} />}
    </svg>
  );
}

export default function OddOneOut({ puzzle, showSolution, locked, onSolved }) {
  const [message, setMessage] = useState("");

  function pick(index) {
    if (locked) return;
    if (isSolved(puzzle, index)) {
      setMessage("");
      onSolved();
    } else {
      setMessage("Not quite, try another");
    }
  }

  if (puzzle.kind === "next") {
    return (
      <div className="brk-game">
        <p className="brk-instruction">What comes next?</p>
        <div
          className="brk-sequence"
          role="img"
          aria-label={`Sequence: ${puzzle.sequence.map((c) => `${c.fill} ${c.shape}`).join(", ")}, then the next one is missing`}
        >
          {puzzle.sequence.map((c, i) => (
            <span key={i} className="brk-seq-cell">
              <Glyph shape={c.shape} fill={c.fill} />
            </span>
          ))}
          <span className="brk-seq-cell brk-seq-missing" aria-hidden="true">
            ?
          </span>
        </div>
        <div className="brk-options" role="group" aria-label="Choose the next shape">
          {puzzle.options.map((c, i) => {
            const isAnswer = showSolution && i === puzzle.answerIndex;
            return (
              <button
                key={i}
                type="button"
                className={`brk-cell ${isAnswer ? "brk-cell-odd" : ""}`}
                disabled={locked}
                onClick={() => pick(i)}
                aria-label={`Option ${i + 1}: ${c.fill} ${c.shape}${isAnswer ? " (this is the answer)" : ""}`}
              >
                <Glyph shape={c.shape} fill={c.fill} />
                {isAnswer && <span className="brk-cell-tag">This one</span>}
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

  return (
    <div className="brk-game">
      <p className="brk-instruction">One of these is different. Which one?</p>
      <div className="brk-grid" role="group" aria-label="Pick the odd one out">
        {puzzle.cells.map((cell, i) => {
          const isOdd = showSolution && i === puzzle.oddIndex;
          return (
            <button
              key={i}
              type="button"
              className={`brk-cell ${isOdd ? "brk-cell-odd" : ""}`}
              disabled={locked}
              onClick={() => pick(i)}
              aria-label={`${cell.fill} ${cell.shape}${isOdd ? " (this is the odd one)" : ""}`}
            >
              <Glyph shape={cell.shape} fill={cell.fill} />
              {isOdd && <span className="brk-cell-tag">This one</span>}
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
