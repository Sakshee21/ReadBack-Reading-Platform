import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";
import { logEvent } from "../api";
import {
  evaluateBreak,
  initialClock,
  loadClock,
  recordOffer,
  recordSessionComplete,
  recordSessionStart,
  saveClock,
} from "./breakClock";
import { breakReducer, initialBreakState } from "./breakReducer";
import { getGame, gameIds } from "./registry";
import { nextGameId } from "./rotation";
import { randomSeed } from "./rng";
import { roundCount } from "./rounds";

const CLOCK_KEY = "readback_break_clock";

// Used when localStorage is blocked: breaks still work, they just won't
// survive a reload.
const memoryStore = (() => {
  const data = {};
  return {
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => {
      data[k] = v;
    },
  };
})();

function pickStorage() {
  try {
    const s = window.localStorage;
    s.getItem(CLOCK_KEY);
    return s;
  } catch {
    return memoryStore;
  }
}

// Development-only demo shortcut: ?break=now makes the first eligible
// completed session trigger the offer without 10 minutes of reading.
function devForced() {
  return Boolean(
    import.meta.env.DEV && new URLSearchParams(window.location.search).get("break") === "now"
  );
}

/**
 * Orchestrates the optional reading break: decides when one is due, shows the
 * offer once the celebration has cleared, runs the game phases, logs every
 * step, and hands control back to the Reader through `resume`.
 */
export function useBreakFlow({ enabled, celebrationActive, resume }) {
  const [state, dispatch] = useReducer(breakReducer, initialBreakState);

  const storageRef = useRef(null);
  if (storageRef.current === null) storageRef.current = pickStorage();
  // Other tabs write the same clock, so every operation re-reads it from
  // storage instead of trusting a copy loaded at mount.
  const readClock = useCallback(() => loadClock(storageRef.current, CLOCK_KEY), []);

  const ctxRef = useRef({});
  const offerActiveMsRef = useRef(0);
  const offeredAtRef = useRef(0);
  const forceRef = useRef(devForced());
  const resumeRef = useRef(resume);
  resumeRef.current = resume;
  const resumedRef = useRef(true);
  const actedRef = useRef(true);
  const gameStartedAtRef = useRef(0);

  const setClock = useCallback((clock) => {
    saveClock(storageRef.current, CLOCK_KEY, clock);
  }, []);

  const log = useCallback((type, extra = {}) => {
    logEvent(type, {
      ...ctxRef.current,
      active_ms_since_last_break: offerActiveMsRef.current,
      ...extra,
    });
  }, []);

  const onSessionStart = useCallback(() => {
    setClock(recordSessionStart(readClock() ?? initialClock(), Date.now()));
  }, [readClock, setClock]);

  // Quiz time is not rest: stamp "now" so a long quiz is not mistaken for an
  // away gap that would wipe a break deferred for that quiz.
  const onQuizDone = useCallback(() => {
    setClock({ ...readClock(), lastSessionEndAt: Date.now() });
  }, [readClock, setClock]);

  // Returns true when a break is now pending, so the Reader skips its autoplay
  // countdown. A quiz due next defers the break (the clock keeps running).
  const onSessionComplete = useCallback(
    ({ activeMs, quizDue, finished, ctx }) => {
      ctxRef.current = ctx || {};
      try {
        const now = Date.now();
        const clock = recordSessionComplete(readClock(), activeMs, now);
        setClock(clock);

        const decision = evaluateBreak(clock, { finished, quizDue, enabled, now });
        let due = decision.due;
        if (!due && forceRef.current && enabled && !finished && !quizDue) {
          due = true;
          forceRef.current = false;
        }

        if (decision.deferredReason) {
          logEvent("break_deferred", {
            ...ctxRef.current,
            reason: decision.deferredReason,
            active_ms_since_last_break: clock.activeMs,
          });
        }
        if (due) {
          offerActiveMsRef.current = clock.activeMs;
          dispatch({ type: "MARK_DUE" });
        }
        return due;
      } catch (err) {
        // A bug in the break logic must never cost the reader their progress.
        console.warn("break evaluation failed:", err);
        return false;
      }
    },
    [enabled, readClock, setClock]
  );

  // Drops a pending (not yet shown) break, e.g. when the reader jumps to
  // another session. The clock is untouched, so the next boundary re-offers.
  const cancelDue = useCallback(() => dispatch({ type: "CANCEL_DUE" }), []);

  // The offer waits until the celebration has cleared so overlays never stack.
  useEffect(() => {
    if (state.phase !== "due" || celebrationActive) return;
    log("break_offered");
    setClock(recordOffer(readClock(), Date.now()));
    offeredAtRef.current = Date.now();
    resumedRef.current = false;
    actedRef.current = false;
    dispatch({ type: "SHOW_OFFER" });
  }, [state.phase, celebrationActive, log, readClock, setClock]);

  const registered = getGame(state.gameId);
  const { puzzle, failed } = useMemo(() => {
    if (!registered) return { puzzle: null, failed: state.phase === "playing" };
    try {
      return { puzzle: registered.generate(state.seed), failed: false };
    } catch {
      return { puzzle: null, failed: true };
    }
  }, [registered, state.seed, state.phase]);
  const game = failed ? null : registered;

  const accept = useCallback(() => {
    if (actedRef.current) return; // a fast double click must act once
    actedRef.current = true;
    const id = nextGameId(gameIds(), storageRef.current, Math.random);
    const seed = randomSeed();
    log("break_accepted");
    log("break_game_start", { game_id: id, seed });
    gameStartedAtRef.current = Date.now();
    dispatch({ type: "ACCEPT", gameId: id, seed });
  }, [log]);

  const decline = useCallback(() => {
    if (actedRef.current) return;
    actedRef.current = true;
    log("break_declined", { response_ms: Date.now() - offeredAtRef.current });
    dispatch({ type: "DECLINE" });
    resumedRef.current = true;
    resumeRef.current();
  }, [log]);

  const finish = useCallback(
    (outcome, durationMs, details = {}) => {
      if (state.phase !== "playing") return;
      log("break_game_end", { game_id: state.gameId, outcome, duration_ms: durationMs, ...details });
      dispatch({ type: "FINISH", outcome });
    },
    [log, state.phase, state.gameId]
  );

  const done = useCallback(() => {
    if (resumedRef.current) return;
    resumedRef.current = true;
    log("break_back_to_reading");
    dispatch({ type: "DONE" });
    resumeRef.current();
  }, [log]);

  // No game to show (empty registry, unknown id, or a generator that threw):
  // end the break as skipped and hand the reader straight back to reading.
  useEffect(() => {
    if (state.phase !== "playing" || !failed) return;
    log("break_game_error", { game_id: state.gameId });
    dispatch({ type: "FINISH", outcome: "skipped" });
    done();
  }, [state.phase, state.gameId, failed, log, done]);

  const onGameError = useCallback(() => {
    log("break_game_error", { game_id: state.gameId });
  }, [log, state.gameId]);

  // Best effort: closing the tab mid-game is recorded as skipped.
  useEffect(() => {
    if (state.phase !== "playing") return;
    const onHide = () =>
      log("break_game_end", {
        game_id: state.gameId,
        outcome: "skipped",
        duration_ms: Date.now() - gameStartedAtRef.current,
        rounds: roundCount(game, state.seed),
      });
    window.addEventListener("pagehide", onHide);
    return () => window.removeEventListener("pagehide", onHide);
  }, [state.phase, state.gameId, state.seed, game, log]);

  return {
    phase: state.phase,
    game,
    puzzle,
    seed: state.seed,
    rounds: roundCount(game, state.seed),
    onSessionStart,
    onSessionComplete,
    cancelDue,
    onQuizDone,
    startedAt: gameStartedAtRef.current,
    accept,
    decline,
    finish,
    done,
    onGameError,
  };
}
