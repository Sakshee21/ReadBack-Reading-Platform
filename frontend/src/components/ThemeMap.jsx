import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, logEvent } from "../api";
import {
  BY_CHAPTER,
  BY_PASSAGE,
  MIN_CELL_PX,
  READ_SO_FAR,
  WHOLE_BOOK,
  cellsByChapter,
  cellsInRange,
  chapterTitle,
  chaptersInRange,
  columnCount,
  shortChapterLabel,
  thinChapterLabels,
} from "../themes/themeMap";

const STRENGTH = { 3: "light", 4: "clear", 5: "strong" };
const plural = (n) => `${n} passage${n === 1 ? "" : "s"}`;

/**
 * Where each theme sits across the book: a row per theme, a cell per tagged
 * passage (or per chapter) in book order.
 *
 * Only passages the reader has reached are ever tagged, and that is decided on
 * the server. Nothing here can widen what is shown: the two controls change
 * how the same data is drawn - how much of the book the chart spans, and
 * whether a cell is a passage or a chapter - not what was asked for.
 */
export default function ThemeMap({ bookId }) {
  const numericBookId = Number(bookId);
  const [map, setMap] = useState(null);
  const [scale, setScale] = useState(READ_SO_FAR);
  const [view, setView] = useState(BY_PASSAGE);
  const [failed, setFailed] = useState(false);
  const request = useRef(0); // only the latest request may set the map
  const openedLogged = useRef(false);

  useEffect(() => {
    const mine = ++request.current;
    setFailed(false);
    (async () => {
      try {
        const data = await api.getThemeMap(bookId);
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
  }, [bookId, numericBookId]);

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

  function changeScale(next) {
    setScale(next);
    logEvent("theme_map_scale_changed", { bookId: numericBookId, scale: next });
  }
  function changeView(next) {
    setView(next);
    logEvent("theme_map_view_changed", { bookId: numericBookId, view: next });
  }

  const passageColumns = columnCount({ total: map.total, reached: map.reached, scale });
  const chapters = chaptersInRange(map.chapters, passageColumns);
  const byChapter = view === BY_CHAPTER;
  // By chapter, a column is a chapter; by passage, a column is a passage.
  const columnTotal = byChapter ? Math.max(1, chapters.length) : passageColumns;
  const grid = {
    gridTemplateColumns: `repeat(${columnTotal}, minmax(${MIN_CELL_PX}px, 1fr))`,
  };
  const labelled = byChapter ? chapters : thinChapterLabels(chapters);
  const ordinalOf = new Map(chapters.map((c, i) => [c.index, i + 1]));
  const columnOf = new Map(chapters.map((c, i) => [c.index, i]));

  const partial = scale === READ_SO_FAR && map.reached > 0 && map.reached < map.total;

  function cellsFor(theme) {
    const within = cellsInRange(theme.cells, passageColumns);
    if (!byChapter) {
      return within.map((cell) => {
        const chapter = chapters.find((c) => c.start <= cell.pos && cell.pos <= c.end);
        const where = chapter ? chapterTitle(chapter) : "";
        return {
          key: cell.micro_session_id,
          column: cell.pos + 1,
          score: cell.score,
          micro_session_id: cell.micro_session_id,
          name:
            `${theme.label}, ${STRENGTH[cell.score] ?? "mentioned"} (${cell.score} of 5)` +
            (where ? `, ${where}` : ""),
        };
      });
    }
    return cellsByChapter(within, chapters).map((cell) => ({
      key: `ch-${cell.chapter.index}`,
      column: (columnOf.get(cell.chapter.index) ?? 0) + 1,
      score: cell.score,
      micro_session_id: cell.micro_session_id,
      name:
        `${theme.label}, ${STRENGTH[cell.score] ?? "mentioned"} (${cell.score} of 5), ` +
        `${chapterTitle(cell.chapter)}, ${plural(cell.count)}`,
    }));
  }

  return (
    <section className="theme-map">
      <h2>Theme map</h2>
      {errorNote}
      <p className="themes-note">
        {byChapter
          ? "Each square is a chapter, at the strength of its strongest passage."
          : "Each square is a passage where the theme is clear."}{" "}
        Darker means stronger.
        {scale === READ_SO_FAR
          ? " Only passages you have reached are shown."
          : " The chart spans the whole book; only passages you have reached are tagged."}
      </p>

      <ul className="map-key" aria-label="Strength key">
        {[3, 4, 5].map((score) => (
          <li key={score}>
            <span className={`map-key-swatch map-score-${score}`} aria-hidden="true" />
            {STRENGTH[score]} ({score} of 5)
          </li>
        ))}
      </ul>

      {map.themes.length === 0 ? (
        <p className="notes-empty">No theme tags to map yet.</p>
      ) : (
        <div
          className="map-scroll"
          tabIndex={0}
          role="group"
          aria-label="Theme map, scrollable sideways"
        >
          <div className="map-plot">
            <div className="map-grid map-chapters" style={grid} aria-hidden="true">
              {labelled.map((c) => (
                <span
                  key={c.index}
                  className="map-chapter"
                  style={{
                    gridColumn: byChapter
                      ? `${(columnOf.get(c.index) ?? 0) + 1} / span 1`
                      : `${c.start + 1} / ${c.end + 2}`,
                  }}
                  title={chapterTitle(c)}
                >
                  {shortChapterLabel(c, ordinalOf.get(c.index) ?? 1)}
                </span>
              ))}
            </div>

            {/* Chapter boundaries, drawn once behind every row. */}
            <div className="map-rules" style={grid} aria-hidden="true">
              {chapters.map((c) => (
                <span
                  key={c.index}
                  className="map-rule"
                  style={{
                    gridColumn: byChapter
                      ? `${(columnOf.get(c.index) ?? 0) + 1}`
                      : `${c.start + 1}`,
                  }}
                />
              ))}
            </div>

            {map.themes.map((t) => {
              const cells = cellsFor(t);
              return (
                <div
                  key={t.theme}
                  className="map-row"
                  role="group"
                  aria-label={`${t.label}: ${plural(t.count)}`}
                >
                  <span className="map-label">{t.label}</span>
                  <div className="map-grid" style={grid}>
                    {cells.map((cell, i) => (
                      <Link
                        key={cell.key}
                        to={`/read/${bookId}?ms=${cell.micro_session_id}`}
                        className={`map-cell map-score-${cell.score}`}
                        style={{ gridColumn: cell.column }}
                        aria-label={cell.name}
                        title={cell.name}
                        tabIndex={i === 0 ? 0 : -1}
                        onKeyDown={moveAlongRow}
                        onClick={() =>
                          logEvent("theme_map_cell_opened", {
                            bookId: numericBookId,
                            theme: t.theme,
                          })
                        }
                      />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="map-controls">
        <div className="map-toggle" role="group" aria-label="What a square stands for">
          <button
            type="button"
            className="btn-secondary"
            aria-pressed={!byChapter}
            onClick={() => changeView(BY_PASSAGE)}
          >
            By passage
          </button>
          <button
            type="button"
            className="btn-secondary"
            aria-pressed={byChapter}
            onClick={() => changeView(BY_CHAPTER)}
          >
            By chapter
          </button>
        </div>

        {scale === WHOLE_BOOK ? (
          <button
            type="button"
            className="btn-secondary"
            onClick={() => changeScale(READ_SO_FAR)}
          >
            Show only what I&rsquo;ve read
          </button>
        ) : (
          <button
            type="button"
            className="btn-secondary"
            disabled={!partial}
            title={partial ? undefined : "You have reached the end of the book."}
            onClick={() => changeScale(WHOLE_BOOK)}
          >
            Show the whole book
          </button>
        )}
      </div>
    </section>
  );
}
