import { useEffect, useRef, useState } from "react";
import { API_URL, logEvent } from "../api";

export default function VisualizationPrompt({
  bookId = null,
  chapterId = null,
  microSessionId = null,
  image = null,
  alt = null,
  attribution = null,
}) {
  const [revealed, setRevealed] = useState(false);
  const shownAt = useRef(Date.now());

  useEffect(() => {
    shownAt.current = Date.now();
    setRevealed(false);
    logEvent("visualization_prompt_shown", { bookId, chapterId, microSessionId, has_image: Boolean(image) });
  }, [bookId, chapterId, microSessionId, image]);

  function handleReveal() {
    setRevealed(true);
    logEvent("visualization_revealed", {
      bookId,
      chapterId,
      microSessionId,
      has_image: Boolean(image),
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
      ) : image ? (
        <figure className="viz-artwork-figure">
          <img className="viz-artwork-image" src={`${API_URL}/static/${image}`} alt={alt || ""} />
          {attribution && <figcaption className="viz-attribution">{attribution}</figcaption>}
        </figure>
      ) : (
        <div className="viz-artwork">Artwork placeholder</div>
      )}
    </div>
  );
}
