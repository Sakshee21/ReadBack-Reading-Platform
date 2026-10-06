import { useEffect, useRef, useState } from "react";
import { logEvent } from "../api";

/**
 * "Picture this scene" checkpoint - imagination only.
 *
 * There is deliberately NO artwork reveal. Showing a picture would supply the
 * very imagery that reading is supposed to make the reader generate, which is
 * the dual-coding mechanism the whole project rests on. Instead the reader is
 * asked to rate how vivid their own mental picture was, which gives the pilot
 * a per-scene imagery measure to sit alongside the VVIQ.
 *
 * The rating is optional: skipping it must never hold up reading or the
 * autoplay countdown.
 */

const RATINGS = [1, 2, 3, 4, 5];
const RATING_HINT = { 1: "barely any picture", 5: "vivid, almost seen" };

export default function VisualizationPrompt({
  bookId = null,
  chapterId = null,
  microSessionId = null,
}) {
  const [rating, setRating] = useState(null);
  const [dismissed, setDismissed] = useState(false);
  const shownAt = useRef(Date.now());

  useEffect(() => {
    shownAt.current = Date.now();
    setRating(null);
    setDismissed(false);
    logEvent("visualization_prompt_shown", { bookId, chapterId, microSessionId });
  }, [bookId, chapterId, microSessionId]);

  if (dismissed) return null;

  function rate(value) {
    setRating(value);
    logEvent("visualization_vividness_rated", {
      bookId,
      chapterId,
      microSessionId,
      rating: value,
      time_to_rate_ms: Date.now() - shownAt.current,
    });
  }

  function dismiss() {
    setDismissed(true);
    logEvent("visualization_prompt_dismissed", {
      bookId,
      chapterId,
      microSessionId,
      rated: rating !== null,
    });
  }

  return (
    <div className="viz-prompt">
      <p>Picture this scene before continuing...</p>

      {rating === null ? (
        <>
          <div className="viz-rating-label">How vivid was it?</div>
          <div className="viz-rating" role="group" aria-label="How vivid was your mental picture?">
            {RATINGS.map((value) => (
              <button
                key={value}
                className="viz-rating-btn"
                onClick={() => rate(value)}
                aria-label={`${value} out of 5${RATING_HINT[value] ? ` - ${RATING_HINT[value]}` : ""}`}
              >
                {value}
              </button>
            ))}
          </div>
          <div className="viz-rating-scale">
            <span>{RATING_HINT[1]}</span>
            <span>{RATING_HINT[5]}</span>
          </div>
          <button className="btn-link viz-skip" onClick={dismiss}>
            Skip
          </button>
        </>
      ) : (
        <div className="viz-rated">
          <span>Thanks - noted {rating}/5.</span>
          <button className="btn-link" onClick={dismiss}>
            Hide
          </button>
        </div>
      )}
    </div>
  );
}
