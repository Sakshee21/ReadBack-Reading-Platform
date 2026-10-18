import { useRef, useState } from "react";
import { checkAnagram, hint, tryStep } from "./wordPlay";

const REASONS = {
  length: "Use 4 letters",
  not_a_word: "Not a word we know",
  not_one_letter: "Change exactly one letter",
  repeat: "Already used",
};

export default function WordPlayGame({ puzzle, showSolution, locked, onSolved }) {
  const [chain, setChain] = useState(puzzle.kind === "ladder" ? [puzzle.start] : []);
  const [value, setValue] = useState("");
  const [message, setMessage] = useState("");
  const [hintTick, setHintTick] = useState(0);
  const solvedRef = useRef(false);
  const disabled = locked || showSolution;

  function finish() {
    if (solvedRef.current) return;
    solvedRef.current = true;
    onSolved();
  }

  function submit(e) {
    e.preventDefault();
    if (disabled) return;
    if (puzzle.kind === "ladder") {
      const result = tryStep(puzzle, chain, value);
      if (!result.ok) {
        setMessage(REASONS[result.reason]);
        return;
      }
      setChain(result.chain);
      setValue("");
      setMessage("");
      if (result.solved) finish();
    } else if (checkAnagram(puzzle, value)) {
      setMessage("");
      finish();
    } else {
      setMessage("Not quite, try another");
    }
  }

  function showHint() {
    if (disabled) return;
    setHintTick((t) => t + 1);
    if (puzzle.kind !== "ladder") {
      setMessage(`Starts with ${hint(puzzle)}`);
      return;
    }
    const next = hint(puzzle, chain);
    setMessage(next ? `Try: ${next}` : "No way forward from here, try Undo last word");
  }

  function undo() {
    if (disabled || chain.length <= 1) return;
    setChain(chain.slice(0, -1));
    setMessage("");
  }

  const ladder = puzzle.kind === "ladder";
  const shownChain = showSolution && ladder ? puzzle.path : chain;

  return (
    <div className="brk-game">
      {ladder ? (
        <>
          <p className="brk-instruction">
            Change one letter at a time to get from <strong>{puzzle.start}</strong> to <strong>{puzzle.target}</strong>.
          </p>
          <ol className="brk-chain">
            {shownChain.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ol>
        </>
      ) : (
        <>
          <p className="brk-instruction">Unscramble these letters into a word.</p>
          <p className="brk-letters" aria-label="Scrambled letters">
            {puzzle.scrambled.toUpperCase().split("").join(" ")}
          </p>
          {showSolution && <p className="brk-answer">Answer: {puzzle.word}</p>}
        </>
      )}

      <form className="brk-word-form" onSubmit={submit}>
        <input
          type="text"
          className="brk-input"
          value={value}
          autoComplete="off"
          autoCorrect="off"
          autoCapitalize="none"
          spellCheck={false}
          disabled={disabled}
          aria-label={ladder ? "Next word" : "Your answer"}
          onChange={(e) => setValue(e.target.value)}
        />
        <button type="submit" className="btn-primary" style={{ width: "auto" }} disabled={disabled}>
          {ladder ? "Add word" : "Check"}
        </button>
        <button type="button" className="btn-secondary" disabled={disabled} onClick={showHint}>
          Hint
        </button>
        {ladder && (
          <button
            type="button"
            className="btn-secondary"
            disabled={disabled || chain.length <= 1}
            onClick={undo}
          >
            Undo last word
          </button>
        )}
      </form>
      <p className="brk-feedback" aria-live="polite">
        {message}
        {/* A repeated hint is identical text, which screen readers skip; this invisible toggle makes it a change. */}
        {hintTick % 2 === 1 ? " " : ""}
      </p>
    </div>
  );
}
