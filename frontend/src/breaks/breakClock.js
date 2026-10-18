import { AWAY_RESET_MS, BREAK_AFTER_ACTIVE_MS, MAX_OFFERS_PER_DAY } from "./constants";

// Pure functions over the "active reading time since the last break" clock.
// Shape: { activeMs, lastSessionEndAt, offersToday, offersDay }

const MAX_SINGLE_ADD_MS = 2 * 60 * 60 * 1000;

export function initialClock() {
  return { activeMs: 0, lastSessionEndAt: null, offersToday: 0, offersDay: null };
}

export function clockDay(ts) {
  const d = new Date(ts);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function recordSessionStart(clock, now) {
  if (clock.lastSessionEndAt !== null && now - clock.lastSessionEndAt >= AWAY_RESET_MS) {
    return { ...clock, activeMs: 0 };
  }
  return clock;
}

export function recordSessionComplete(clock, activeMs, now) {
  const valid = typeof activeMs === "number" && Number.isFinite(activeMs) && activeMs >= 0;
  const added = valid ? Math.min(activeMs, MAX_SINGLE_ADD_MS) : 0;
  return { ...clock, activeMs: clock.activeMs + added, lastSessionEndAt: now };
}

function offersTodayCount(clock, now) {
  return clock.offersDay === clockDay(now) ? clock.offersToday : 0;
}

export function evaluateBreak(clock, { finished, quizDue, enabled, now }) {
  if (!enabled || finished) return { due: false, deferredReason: null };
  if (offersTodayCount(clock, now) >= MAX_OFFERS_PER_DAY) return { due: false, deferredReason: null };
  if (clock.activeMs < BREAK_AFTER_ACTIVE_MS) return { due: false, deferredReason: null };
  if (quizDue) return { due: false, deferredReason: "quiz_due" };
  return { due: true, deferredReason: null };
}

export function recordOffer(clock, now) {
  return {
    ...clock,
    activeMs: 0,
    offersToday: offersTodayCount(clock, now) + 1,
    offersDay: clockDay(now),
  };
}

function isValidClock(c) {
  return (
    c !== null &&
    typeof c === "object" &&
    !Array.isArray(c) &&
    Number.isFinite(c.activeMs) &&
    (c.lastSessionEndAt === null || Number.isFinite(c.lastSessionEndAt)) &&
    Number.isFinite(c.offersToday) &&
    (c.offersDay === null || typeof c.offersDay === "string")
  );
}

export function loadClock(storage, key) {
  try {
    const parsed = JSON.parse(storage.getItem(key));
    return isValidClock(parsed) ? parsed : initialClock();
  } catch {
    return initialClock();
  }
}

export function saveClock(storage, key, clock) {
  try {
    storage.setItem(key, JSON.stringify(clock));
  } catch {
    // storage unavailable - the clock just won't survive a reload
  }
}
