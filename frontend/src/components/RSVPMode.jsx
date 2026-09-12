import { useEffect, useMemo, useState } from "react";

export default function RSVPMode({ text, onExit }) {
  const words = useMemo(() => text.split(/\s+/).filter(Boolean), [text]);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [wpm, setWpm] = useState(300);

  useEffect(() => {
    if (!playing) return;
    if (index >= words.length) return;
    const delay = 60000 / wpm;
    const timer = setTimeout(() => setIndex((i) => i + 1), delay);
    return () => clearTimeout(timer);
  }, [playing, index, wpm, words.length]);

  const done = index >= words.length;
  const currentWord = done ? "" : words[index];

  return (
    <div className="rsvp-overlay">
      <div className="rsvp-word">{done ? "Done" : currentWord}</div>

      {done ? (
        <button className="btn-primary" style={{ width: "auto", marginTop: "1.5rem" }} onClick={onExit}>
          Back to reading
        </button>
      ) : (
        <div className="rsvp-controls">
          <button className="btn-secondary" onClick={() => setPlaying((p) => !p)}>
            {playing ? "Pause" : "Play"}
          </button>
          <label>
            {wpm} wpm
            <input
              type="range"
              min={100}
              max={600}
              step={25}
              value={wpm}
              onChange={(e) => setWpm(Number(e.target.value))}
              style={{ marginLeft: "0.5rem", verticalAlign: "middle" }}
            />
          </label>
          <button className="btn-secondary" onClick={onExit}>
            Exit RSVP
          </button>
        </div>
      )}

      <div className="rsvp-progress">
        {Math.min(index + 1, words.length)} / {words.length} words
      </div>
    </div>
  );
}
