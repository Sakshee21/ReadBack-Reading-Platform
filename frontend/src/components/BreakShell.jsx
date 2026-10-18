import { Component, useCallback, useEffect, useRef, useState } from "react";
import { BREAK_GAME_CAP_MS } from "../breaks/constants";
import { roundSeed } from "../breaks/rounds";
import { useDialogKeys } from "../breaks/useDialogKeys";

// Catches a crashing game so a bug in a puzzle can never block reading.
class GameBoundary extends Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch() {
    this.props.onError();
  }

  render() {
    return this.state.failed ? null : this.props.children;
  }
}

/**
 * The wrapper that enforces every rule about how a break may be played, so no
 * individual game can opt out: a fixed number of puzzles (one, or 3-4 for the
 * quick games), a hard time cap over the whole break, no visible timer, always
 * a way out, one end card with one button, no score or replay.
 */
export default function BreakShell({
  game,
  puzzle: firstPuzzle,
  seed = 0,
  rounds = 1,
  startedAt: startedAtProp,
  onFinish,
  onDone,
  onError,
}) {
  const [status, setStatus] = useState("playing"); // playing | ended
  const [outcome, setOutcome] = useState(null);
  const [round, setRound] = useState(0);
  const [puzzle, setPuzzle] = useState(firstPuzzle);
  const [showSolution, setShowSolution] = useState(false);
  const [between, setBetween] = useState(false); // this puzzle is finished; waiting for "Next puzzle"
  // The cap runs from when the game started (passed in by the flow), so a
  // remount cannot restart it.
  const startedAt = useRef(startedAtProp || Date.now());
  const endedRef = useRef(false);
  const roundDoneRef = useRef(false);
  const progress = useRef({ solved: 0, revealed: false });
  const dialogRef = useRef(null);
  const endButtonRef = useRef(null);
  const nextButtonRef = useRef(null);
  const onFinishRef = useRef(onFinish);
  onFinishRef.current = onFinish;

  const end = useCallback(
    (result) => {
      if (endedRef.current) return false;
      endedRef.current = true;
      setOutcome(result);
      setStatus("ended");
      onFinishRef.current(result, Date.now() - startedAt.current, {
        rounds,
        rounds_solved: progress.current.solved,
      });
      return true;
    },
    [rounds]
  );

  useEffect(() => {
    const remaining = Math.max(0, BREAK_GAME_CAP_MS - (Date.now() - startedAt.current));
    const timer = setTimeout(() => end("time_cap"), remaining);

    // Timers can fire late after a laptop sleep or a throttled background tab,
    // so also check the deadline whenever the page comes back.
    const check = () => {
      if (Date.now() - startedAt.current >= BREAK_GAME_CAP_MS) end("time_cap");
    };
    document.addEventListener("visibilitychange", check);
    window.addEventListener("focus", check);
    return () => {
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", check);
      window.removeEventListener("focus", check);
    };
  }, [end]);

  const skip = useCallback(() => {
    if (end("skipped")) onDone();
  }, [end, onDone]);

  // A puzzle is finished: either move to the "Next puzzle" pause, or, on the
  // last one, end the break with the overall outcome.
  const finishRound = useCallback(
    (how) => {
      if (endedRef.current || roundDoneRef.current) return;
      roundDoneRef.current = true;
      if (how === "solved") progress.current.solved += 1;
      else progress.current.revealed = true;

      if (round >= rounds - 1) {
        end(progress.current.revealed ? "shown_solution" : "solved");
      } else {
        setBetween(true);
      }
    },
    [round, rounds, end]
  );

  const revealSolution = useCallback(() => {
    if (endedRef.current || roundDoneRef.current) return;
    setShowSolution(true);
    finishRound("revealed");
  }, [finishRound]);

  // A crashed game, or a later puzzle that cannot be built, ends the break as
  // skipped so reading is never blocked.
  const handleError = useCallback(() => {
    onError();
    if (end("skipped")) onDone();
  }, [onError, end, onDone]);

  const nextPuzzle = useCallback(() => {
    if (endedRef.current || !roundDoneRef.current) return;
    let next;
    try {
      next = game.generate(roundSeed(seed, round + 1));
    } catch {
      handleError();
      return;
    }
    roundDoneRef.current = false;
    setPuzzle(next);
    setRound(round + 1);
    setShowSolution(false);
    setBetween(false);
  }, [game, seed, round, handleError]);

  // Escape skips while playing and goes back to reading from the end card;
  // Tab is kept inside the dialog.
  useDialogKeys(dialogRef, () => {
    if (endedRef.current) onDone();
    else skip();
  });

  // Focus the dialog itself, not its first control: a text game would otherwise
  // pop the on-screen keyboard the moment the break opens.
  useEffect(() => {
    dialogRef.current?.focus();
  }, []);

  // A locked puzzle drops focus, so move it to the only action left.
  useEffect(() => {
    if (status === "ended") endButtonRef.current?.focus();
  }, [status]);
  useEffect(() => {
    if (between) nextButtonRef.current?.focus();
  }, [between]);

  // A new puzzle replaces the "Next puzzle" button with "Show solution" in the
  // same spot, which would leave focus on it and make a double Enter reveal
  // the answer. Park focus on the dialog (not a button) for each new puzzle.
  useEffect(() => {
    if (round > 0) dialogRef.current?.focus();
  }, [round]);

  const ended = status === "ended";
  const Game = game.Component;

  return (
    <div className="brk-overlay">
      <div
        ref={dialogRef}
        className="brk-card brk-card-game"
        role="dialog"
        aria-modal="true"
        aria-label="Short break"
        tabIndex={-1}
      >
        {rounds > 1 && !ended && (
          <p className="brk-progress" aria-live="polite">
            Puzzle {round + 1} of {rounds}
          </p>
        )}

        <GameBoundary key={round} onError={handleError}>
          <Game
            puzzle={puzzle}
            showSolution={showSolution}
            locked={ended || between}
            onSolved={() => finishRound("solved")}
          />
        </GameBoundary>

        {ended ? (
          <div className="brk-end" aria-live="polite">
            <p className="brk-text">
              {outcome === "time_cap"
                ? "Time for a break from the break. Back to the story?"
                : "Nice break. Back to the story?"}
            </p>
            <button
              ref={endButtonRef}
              type="button"
              className="btn-primary"
              style={{ width: "auto" }}
              onClick={onDone}
            >
              Back to reading
            </button>
          </div>
        ) : between ? (
          <div className="brk-actions" aria-live="polite">
            <button
              ref={nextButtonRef}
              type="button"
              className="btn-primary"
              style={{ width: "auto" }}
              onClick={nextPuzzle}
            >
              Next puzzle
            </button>
            <button type="button" className="btn-secondary" onClick={skip}>
              Skip, back to reading
            </button>
          </div>
        ) : (
          <div className="brk-actions">
            <button type="button" className="btn-secondary" onClick={revealSolution}>
              Show solution
            </button>
            <button type="button" className="btn-secondary" onClick={skip}>
              Skip, back to reading
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
