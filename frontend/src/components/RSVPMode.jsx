import { useEffect, useMemo, useRef, useState } from "react";

/**
 * Renders the same paragraphs as the normal reader view, but with the
 * current word highlighted and auto-advancing at the chosen WPM - the page
 * itself never changes, only which word is lit up moves.
 */
export default function RSVPMode({ text, onExit }) {
  const paragraphs = useMemo(() => text.split(/\n{2,}/), [text]);

  const structuredParagraphs = useMemo(() => {
    let globalIndex = 0;
    return paragraphs.map((paragraph) =>
      paragraph
        .split(/\s+/)
        .filter(Boolean)
        .map((word) => ({ word, globalIndex: globalIndex++ }))
    );
  }, [paragraphs]);

  const totalWords = useMemo(
    () => structuredParagraphs.reduce((sum, p) => sum + p.length, 0),
    [structuredParagraphs]
  );

  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [wpm, setWpm] = useState(300);
  const contentRef = useRef(null);

  useEffect(() => {
    if (!playing || index >= totalWords) return;
    const delay = 60000 / wpm;
    const timer = setTimeout(() => setIndex((i) => i + 1), delay);
    return () => clearTimeout(timer);
  }, [playing, index, wpm, totalWords]);

  useEffect(() => {
    const current = contentRef.current?.querySelector(".rsvp-current");
    current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [index]);

  const done = index >= totalWords;

  return (
    <>
      <div className="rsvp-control-bar">
        <button className="btn-secondary" onClick={() => setPlaying((p) => !p)} disabled={done}>
          {playing && !done ? "Pause" : "Play"}
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
          />
        </label>
        <span className="rsvp-word-count">
          {Math.min(index + 1, totalWords)} / {totalWords} words
        </span>
        <button className="btn-secondary" onClick={onExit}>
          Exit RSVP
        </button>
      </div>

      <div ref={contentRef}>
        {structuredParagraphs.map((paragraphWords, pi) => (
          <p key={pi}>
            {paragraphWords.map(({ word, globalIndex }) => (
              <span
                key={globalIndex}
                className={globalIndex === index ? "rsvp-current" : undefined}
              >
                {word}{" "}
              </span>
            ))}
          </p>
        ))}
      </div>
    </>
  );
}
