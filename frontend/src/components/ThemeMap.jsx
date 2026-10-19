import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, logEvent } from "../api";
import { chapterLocator } from "../citations/format";

const STRENGTH = { 3: "light", 4: "clear", 5: "strong" };
const plural = (n) => `${n} passage${n === 1 ? "" : "s"}`;

/**
 * Where each theme sits across the book: a row per theme, a cell per tagged
 * passage in book order. By default only passages the reader has reached are
 * shown; "Show the whole book" is an explicit, per-visit choice that can spoil
 * the story, so it asks first and is never remembered.
 */
export default function ThemeMap({ bookId }) {
  const numericBookId = Number(bookId);
  const [map, setMap] = useState(null);
  const [reveal, setReveal] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [failed, setFailed] = useState(false);
  const request = useRef(0); // only the latest request may set the map
  const openedLogged = useRef(false);

  useEffect(() => {
    const mine = ++request.current;
    setFailed(false);
    (async () => {
      try {
        const data = await api.getThemeMap(bookId, reveal);
        if (mine !== request.current) return;
        setMap(data);
        if (!openedLogged.current) {
          openedLogged.current = true;
          logEvent("theme_map_opened", { bookId: numericBookId });
        }
      } catch {
        if (mine === request.current) setFailed(true);
      }
    })();
  }, [bookId, numericBookId, reveal]);

  function confirmReveal() {
    setConfirming(false);
    setReveal(true);
    logEvent("theme_map_revealed", { bookId: numericBookId });
  }

  const errorNote = failed && (
    <p role="alert" className="hl-error">
      Could not load the theme map. Try again in a moment.
    </p>
  );
  if (!map) {
    return failed ? (
      <section className="theme-map">
        <h2>Theme map</h2>
        {errorNote}
      </section>
    ) : null;
  }

  // A row is one tab stop; the arrow keys move between its squares.
  function moveAlongRow(event) {
    const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    const cells = [...event.currentTarget.parentElement.querySelectorAll("a")];
    const next = cells[cells.indexOf(event.currentTarget) + step];
    if (next) {
      event.preventDefault();
      next.focus();
    }
  }

  const chapterAt = (pos) => map.chapters.find((c) => c.start <= pos && pos <= c.end);
  const columns = { gridTemplateColumns: `repeat(${Math.max(map.total, 1)}, minmax(2px, 1fr))` };

  return (
    <section className="theme-map">
      <h2>Theme map</h2>
      {errorNote}
      <p className="themes-note">
        Each square is a passage where the theme is clear. Darker means stronger.
        {!map.reveal && " Only passages you have reached are shown."}
      </p>

      {map.themes.length === 0 ? (
        <p className="notes-empty">No theme tags to map yet.</p>
      ) : (
        <div className="map-scroll">
          <div className="map-grid map-chapters" style={columns} aria-hidden="true">
            {map.chapters.map((c) => (
              <span
                key={c.index}
                className="map-chapter"
                style={{ gridColumn: `${c.start + 1} / ${c.end + 2}` }}
                title={c.title || undefined}
              >
                {c.title || chapterLocator({ chapter_title: "", chapter_index: c.index }).label}
              </span>
            ))}
          </div>
          {map.themes.map((t) => (
            <div key={t.theme} className="map-row" role="group" aria-label={`${t.label}: ${plural(t.count)}`}>
              <span className="map-label">{t.label}</span>
              <div className="map-grid" style={columns}>
                {t.cells.map((cell, i) => {
                  const chapter = chapterAt(cell.pos);
                  const where = chapter
                    ? chapterLocator({ chapter_title: chapter.title, chapter_index: chapter.index }).label
                    : "";
                  const name = `${t.label}, ${STRENGTH[cell.score] ?? "mentioned"} (${cell.score} of 5)${where ? `, ${where}` : ""}`;
                  return (
                    <Link
                      key={cell.micro_session_id}
                      to={`/read/${bookId}?ms=${cell.micro_session_id}`}
                      className={`map-cell map-score-${cell.score}`}
                      style={{ gridColumn: cell.pos + 1 }}
                      aria-label={name}
                      title={name}
                      tabIndex={i === 0 ? 0 : -1}
                      onKeyDown={moveAlongRow}
                      onClick={() => logEvent("theme_map_cell_opened", { bookId: numericBookId, theme: t.theme })}
                    />
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="map-reveal">
        {reveal ? (
          <button type="button" className="btn-secondary" onClick={() => setReveal(false)}>
            Hide unread parts
          </button>
        ) : confirming ? (
          <>
            <p>
              This shows where themes appear in parts you have not read yet. It may spoil the story.
            </p>
            <button type="button" className="btn-secondary" onClick={confirmReveal}>
              Show it anyway
            </button>{" "}
            <button type="button" className="btn-secondary" onClick={() => setConfirming(false)}>
              Cancel
            </button>
          </>
        ) : (
          <button type="button" className="btn-secondary" onClick={() => setConfirming(true)}>
            Show the whole book
          </button>
        )}
      </div>
    </section>
  );
}
