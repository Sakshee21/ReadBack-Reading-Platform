// Small pure helpers the Reader uses for highlighting.

/** Highlighting is offered only while nothing else owns the screen. */
export function highlightingEnabled({
  rsvpActive,
  celebrationActive,
  drawerOpen,
  settingsOpen,
  quizDue,
  unstuckPrompt,
  burstActive,
  countdownActive,
  breakPhase,
}) {
  return !(
    rsvpActive ||
    celebrationActive ||
    drawerOpen ||
    settingsOpen ||
    quizDue ||
    unstuckPrompt ||
    burstActive ||
    countdownActive ||
    breakPhase !== "idle"
  );
}

const positiveInt = (value) => {
  if (value === null || !/^\d+$/.test(value)) return null;
  const n = Number(value);
  return n > 0 ? n : null;
};

/** `?ms=<micro-session id>&h=<highlight id>` from the notes page. */
export function parseDeepLink(search) {
  const params = new URLSearchParams(search);
  return { ms: positiveInt(params.get("ms")), h: positiveInt(params.get("h")) };
}

/**
 * Open at a given micro-session when asked, else at the saved position. The
 * request is a read-only peek, so following a note does not move the reader's
 * saved place.
 */
export async function loadInitialPosition(api, bookId, microSessionId) {
  if (microSessionId) {
    try {
      return await api.getReaderPosition(bookId, microSessionId);
    } catch {
      // The passage is gone or not ours: just open where the reader left off.
    }
  }
  return api.getReaderPosition(bookId);
}

/** The micro-sessions inside the served block; highlights attach to these. */
export function partsOf(microSession) {
  return microSession.parts?.length
    ? microSession.parts
    : [{ id: microSession.id, text: microSession.text }];
}
