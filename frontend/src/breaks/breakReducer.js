import { OUTCOMES } from "./constants";

export const initialBreakState = { phase: "idle", gameId: null, seed: null, outcome: null };

// idle -> due -> offered -> playing -> ended -> idle. Any action that is not
// valid in the current phase returns the same state object.
export function breakReducer(state, action) {
  switch (action.type) {
    case "MARK_DUE":
      return state.phase === "idle" ? { ...state, phase: "due" } : state;
    case "CANCEL_DUE":
      return state.phase === "due" ? initialBreakState : state;
    case "SHOW_OFFER":
      return state.phase === "due" ? { ...state, phase: "offered" } : state;
    case "ACCEPT":
      return state.phase === "offered"
        ? { phase: "playing", gameId: action.gameId, seed: action.seed, outcome: null }
        : state;
    case "DECLINE":
      return state.phase === "offered" ? initialBreakState : state;
    case "FINISH":
      return state.phase === "playing" && OUTCOMES.includes(action.outcome)
        ? { ...state, phase: "ended", outcome: action.outcome }
        : state;
    case "DONE":
      return state.phase === "ended" ? initialBreakState : state;
    default:
      return state;
  }
}
