import { useEffect, useRef, useState } from "react";
import { logEvent } from "../api";

export default function VisualizationPrompt({ bookId = null, chapterId = null, microSessionId = null }) {
  const [revealed, setRevealed] = useState(false);
  const shownAt = useRef(Date.now());

  useEffect(() => {
    shownAt.current = Date.now();
    logEvent("visualization_prompt_shown", { bookId, chapterId, microSessionId });
  }, [bookId, chapterId, microSessionId]);

  function handleReveal() {
    setRevealed(true);
    logEvent("visualization_revealed", {
      bookId,
      chapterId,
      microSessionId,
      time_to_reveal_ms: Date.now() - shownAt.current,
    });
  }

  return (
    <div className="viz-prompt">
      <p>Picture this scene before continuing...</p>
      {!revealed ? (
        <button className="btn-secondary" onClick={handleReveal}>
          Reveal artwork
        </button>
      ) : (
        <div className="viz-artwork">Artwork placeholder</div>
      )}
    </div>
  );
}
