import { useState } from "react";

export default function VisualizationPrompt() {
  const [revealed, setRevealed] = useState(false);

  return (
    <div className="viz-prompt">
      <p>Picture this scene before continuing...</p>
      {!revealed ? (
        <button className="btn-secondary" onClick={() => setRevealed(true)}>
          Reveal artwork
        </button>
      ) : (
        <div className="viz-artwork">Artwork placeholder</div>
      )}
    </div>
  );
}
