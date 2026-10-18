import { useEffect, useState } from "react";
import { clearMismatch, flip, initialState, isComplete } from "./matchingCards";

const MISMATCH_MS = 800;

export default function MatchingCardsGame({ puzzle, showSolution, locked, onSolved }) {
  const [state, setState] = useState(initialState);
  const [message, setMessage] = useState("");

  // Mismatched cards turn back after a beat. Cleared on unmount and as soon as
  // the shell locks the game, so nothing changes after the break ends.
  useEffect(() => {
    if (!state.pending || locked) return undefined;
    const timer = setTimeout(() => {
      setState((s) => clearMismatch(s));
      setMessage("");
    }, MISMATCH_MS);
    return () => clearTimeout(timer);
  }, [state.pending, locked]);

  function pick(index) {
    if (locked || showSolution) return;
    const next = flip(puzzle, state, index);
    if (next === state) return;
    setState(next);
    if (next.matched.length > state.matched.length) setMessage("Match!");
    else if (next.pending) setMessage("No match, turning back");
    if (isComplete(puzzle, next)) onSolved();
  }

  return (
    <div className="brk-game">
      <p className="brk-instruction">Find the matching pairs.</p>
      <div className="brk-cards" role="group" aria-label="Matching cards">
        {puzzle.cards.map((c, i) => {
          const matched = state.matched.includes(i);
          const up = showSolution || state.faceUp.includes(i) || matched;
          return (
            <button
              key={i}
              type="button"
              className={`brk-card-tile ${up ? "brk-card-up" : ""} ${matched ? "brk-card-matched" : ""}`}
              aria-disabled={locked || showSolution}
              onClick={() => pick(i)}
              aria-label={`Card ${i + 1}, ${up ? c.name : "face down"}${matched ? ", matched" : ""}`}
            >
              <span aria-hidden="true">{up ? c.symbol : ""}</span>
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
