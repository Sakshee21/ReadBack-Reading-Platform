import { useEffect, useRef, useState } from "react";
import confetti from "canvas-confetti";
import { logEvent } from "../api";
import { useSettings } from "../SettingsContext";

/**
 * Reward animation shown when a micro-session completes.
 *
 * REWARD RULES (deterministic - every pilot user gets the same reward for the
 * same behaviour, so the variable-reward mechanic doesn't contaminate the data):
 *
 *   streak reaches exactly 3  -> "streak_3"   bigger burst, two origins
 *   streak reaches exactly 7  -> "streak_7"   bigger still, three origins
 *   streak reaches exactly 14 -> "streak_14"  largest burst
 *   anything else             -> "session"    small burst + check mark
 *
 * Only the *rule* is deterministic; where individual confetti particles land is
 * cosmetic and is never recorded. Nothing here depicts story content.
 */

export const STREAK_MILESTONES = [3, 7, 14];

export function celebrationFor({ streakBefore, streakAfter }) {
  if (streakAfter !== streakBefore && STREAK_MILESTONES.includes(streakAfter)) {
    return { type: `streak_${streakAfter}`, milestone: streakAfter };
  }
  return { type: "session", milestone: null };
}

const TIERS = {
  session: { particles: 45, spread: 55, origins: [0.5], message: "Session complete" },
  streak_3: { particles: 90, spread: 70, origins: [0.35, 0.65], message: "3-day streak!" },
  streak_7: { particles: 130, spread: 85, origins: [0.25, 0.5, 0.75], message: "7-day streak!" },
  streak_14: { particles: 180, spread: 100, origins: [0.2, 0.4, 0.6, 0.8], message: "14-day streak!" },
};

const VISIBLE_MS = 1600;

export default function CelebrationOverlay({ celebration, bookId, chapterId, microSessionId, onDone }) {
  const { reduceMotion } = useSettings();
  const [dismissed, setDismissed] = useState(false);
  const firedFor = useRef(null);

  const tier = TIERS[celebration?.type] || TIERS.session;

  // onDone is an inline arrow in the parent, so it changes identity on every
  // render. Keeping it in a ref stops the effect below from re-running and
  // clearing its own auto-dismiss timer.
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  const celebrationType = celebration?.type;
  const milestone = celebration?.milestone ?? null;

  useEffect(() => {
    if (!celebrationType) return;
    // StrictMode double-invokes effects in dev; only celebrate once.
    const key = `${celebrationType}-${microSessionId}`;
    if (firedFor.current === key) return;
    firedFor.current = key;

    const spec = TIERS[celebrationType] || TIERS.session;
    setDismissed(false);
    logEvent("celebration_shown", {
      bookId,
      chapterId,
      microSessionId,
      celebration_type: celebrationType,
      streak_milestone: milestone,
      reduced_motion: reduceMotion,
    });

    if (!reduceMotion) {
      for (const x of spec.origins) {
        confetti({
          particleCount: Math.round(spec.particles / spec.origins.length),
          spread: spec.spread,
          startVelocity: 32,
          gravity: 1.1,
          ticks: 120,
          scalar: 0.85,
          disableForReducedMotion: true,
          origin: { x, y: 0.22 },
        });
      }
    }

    const timer = setTimeout(() => {
      setDismissed(true);
      onDoneRef.current?.();
    }, VISIBLE_MS);
    return () => clearTimeout(timer);
  }, [celebrationType, milestone, microSessionId, reduceMotion, bookId, chapterId]);

  if (!celebrationType || dismissed) return null;

  return (
    // pointer-events: none on the wrapper so this can never swallow a click
    // meant for the autoplay countdown underneath it.
    <div className="celebration-layer">
      <button
        className="celebration-badge"
        onClick={() => {
          setDismissed(true);
          onDoneRef.current?.();
        }}
        aria-label={`${tier.message}. Dismiss`}
      >
        <svg className="celebration-check" width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
          <path
            d="M4 12.5l5 5L20 6.5"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <span>{tier.message}</span>
      </button>
    </div>
  );
}
