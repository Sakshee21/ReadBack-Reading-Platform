import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, logEvent } from "../api";
import { HIGHLIGHT_COLORS, colorLabel } from "../highlights/constants";
import { buildNotesMarkdown, chapterHeading, notesFileName } from "../highlights/exportMarkdown";
import { buildNotesCsv, notesCsvFileName } from "../highlights/exportCsv";
import { STYLES } from "../citations/format";
import { useSettings } from "../SettingsContext";
import CiteControl from "../components/CiteControl";

const hueOf = (id) => HIGHLIGHT_COLORS.find((c) => c.id === id)?.hue;
const plural = (n) => `${n} highlight${n === 1 ? "" : "s"}`;

export default function NotesPage() {
  const { bookId } = useParams();
  const numericBookId = Number(bookId);
  const [highlights, setHighlights] = useState([]);
  const [bookTitle, setBookTitle] = useState("");
  const [book, setBook] = useState(null);
  const [citingId, setCitingId] = useState(null);
  const [status, setStatus] = useState("loading"); // loading | ready | failed
  const [filter, setFilter] = useState("all");
  const [editing, setEditing] = useState(null); // {id, color, comment}
  const [confirmingId, setConfirmingId] = useState(null);
  const [actionError, setActionError] = useState("");
  const openedLogged = useRef(false);
  const { citationStyle, setCitationStyle } = useSettings();
  const busyRef = useRef(false); // one save/delete at a time, whatever the clicks

  useEffect(() => {
    let current = true;
    async function load() {
      try {
        const [rows, books] = await Promise.all([api.listHighlights(bookId), api.listBooks()]);
        if (!current) return;
        setHighlights(rows);
        const found = books.find((b) => b.id === numericBookId) || null;
        setBook(found);
        setBookTitle(found?.title || "");
        setStatus("ready");
        if (!openedLogged.current) {
          openedLogged.current = true;
          logEvent("notes_opened", { bookId: numericBookId, count: rows.length });
        }
      } catch {
        if (current) setStatus("failed");
      }
    }
    load();
    return () => {
      current = false;
    };
  }, [bookId, numericBookId]);

  const visible = useMemo(
    () => (filter === "all" ? highlights : highlights.filter((h) => h.color === filter)),
    [highlights, filter]
  );

  const groups = useMemo(() => {
    const ordered = [...visible].sort(
      (a, b) =>
        a.chapter_index - b.chapter_index || a.session_index - b.session_index || a.start - b.start
    );
    const out = [];
    for (const h of ordered) {
      const last = out[out.length - 1];
      if (last && last.chapterIndex === h.chapter_index) last.items.push(h);
      else out.push({ chapterIndex: h.chapter_index, title: chapterHeading(h), items: [h] });
    }
    return out;
  }, [visible]);

  async function saveEdit() {
    if (busyRef.current) return;
    busyRef.current = true;
    setActionError("");
    try {
      const saved = await api.updateHighlight(editing.id, {
        color: editing.color,
        comment: editing.comment.trim() || null,
      });
      logEvent("highlight_edited", {
        bookId: numericBookId,
        color: saved.color,
        has_comment: Boolean(saved.comment),
      });
      setHighlights((all) => all.map((h) => (h.id === saved.id ? { ...h, ...saved } : h)));
      setEditing(null);
    } catch {
      setActionError("Could not save that change. Try again.");
    } finally {
      busyRef.current = false;
    }
  }

  async function remove(id) {
    if (busyRef.current) return;
    busyRef.current = true;
    setActionError("");
    try {
      await api.deleteHighlight(id);
      logEvent("highlight_deleted", { bookId: numericBookId });
      setHighlights((all) => all.filter((h) => h.id !== id));
      setConfirmingId(null);
    } catch {
      setActionError("Could not delete that highlight. Try again.");
    } finally {
      busyRef.current = false;
    }
  }

  function download(fileName, blob, format) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    link.remove();
    // Some browsers cancel the download if the URL goes away during the click.
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    logEvent("notes_exported", { bookId: numericBookId, count: highlights.length, format, style: citationStyle });
  }

  function exportMarkdown() {
    const markdown = buildNotesMarkdown({ bookTitle, highlights, book, style: citationStyle });
    download(notesFileName(bookTitle), new Blob([markdown], { type: "text/markdown;charset=utf-8" }), "markdown");
  }

  function exportCsv() {
    // The byte order mark makes Excel read the file as UTF-8.
    const csv = buildNotesCsv({ book: book || { title: bookTitle, author: "" }, style: citationStyle, highlights });
    download(notesCsvFileName(bookTitle), new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8" }), "csv");
  }

  if (status === "loading") return <div className="page-loading">Loading your notes...</div>;
  if (status === "failed") {
    return (
      <div className="notes-page">
        <p role="alert">Could not load your notes. Try again in a moment.</p>
        <Link to="/library">Library</Link>
      </div>
    );
  }

  return (
    <div className="notes-page">
      <div className="notes-header">
        <h1>Notes{bookTitle ? `: ${bookTitle}` : ""}</h1>
        <nav className="notes-nav">
          <Link to={`/read/${bookId}`} className="btn-secondary">
            Back to reading
          </Link>{" "}
          <Link to={`/books/${bookId}/themes`} className="btn-secondary">
            Themes
          </Link>{" "}
          <Link to="/library" className="btn-secondary">
            Library
          </Link>
        </nav>
      </div>

      {highlights.length === 0 ? (
        <p className="notes-empty">
          No highlights yet. Select any text while reading, then pick a colour to save it here.
        </p>
      ) : (
        <>
          <div className="notes-toolbar">
            <fieldset className="notes-filter">
              <legend>Colour</legend>
              <label>
                <input type="radio" name="note-filter" checked={filter === "all"} onChange={() => setFilter("all")} />{" "}
                All
              </label>
              {HIGHLIGHT_COLORS.map((c) => (
                <label key={c.id}>
                  <input
                    type="radio"
                    name="note-filter"
                    checked={filter === c.id}
                    onChange={() => setFilter(c.id)}
                  />{" "}
                  <span className="hl-dot" style={{ background: c.hue, display: "inline-block" }} aria-hidden="true" />{" "}
                  {c.label}
                </label>
              ))}
            </fieldset>
            <span>{filter === "all" ? plural(highlights.length) : `Showing ${visible.length} of ${highlights.length}`}</span>
            <label className="cite-style">
              <span>Export citation style</span>
              <select value={citationStyle} onChange={(e) => setCitationStyle(e.target.value)}>
                {STYLES.map((id) => (
                  <option key={id} value={id}>
                    {{ apa: "APA 7", mla: "MLA 9", chicago: "Chicago 17" }[id]}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" className="btn-secondary" onClick={exportMarkdown}>
              Export as Markdown
            </button>
            <button type="button" className="btn-secondary" onClick={exportCsv}>
              Export as CSV
            </button>
          </div>
          {actionError && <p role="alert" className="hl-error">{actionError}</p>}

          {visible.length === 0 && (
            <p className="notes-empty">No {colorLabel(filter).toLowerCase()} highlights yet.</p>
          )}

          {groups.map((group) => (
            <section key={group.chapterIndex}>
              <h2 className="notes-chapter">{group.title}</h2>
              {group.items.map((h) => (
                <article key={h.id} className="note-card" style={{ "--hl": hueOf(h.color) }}>
                  <div className="note-meta">
                    <span>
                      <span className="hl-dot" style={{ background: hueOf(h.color), display: "inline-block" }} aria-hidden="true" />{" "}
                      {colorLabel(h.color)}
                    </span>
                    {h.session_number && <span>Session {h.session_number}</span>}
                    <span>{new Date(h.created_at).toLocaleDateString()}</span>
                  </div>
                  <blockquote className="note-quote" data-testid="note-quote">
                    {h.quote}
                  </blockquote>

                  {editing?.id === h.id ? (
                    <div className="note-edit">
                      <fieldset className="notes-filter">
                        <legend>Colour</legend>
                        {HIGHLIGHT_COLORS.map((c) => (
                          <label key={c.id}>
                            <input
                              type="radio"
                              name={`edit-color-${h.id}`}
                              checked={editing.color === c.id}
                              onChange={() => setEditing({ ...editing, color: c.id })}
                            />{" "}
                            {c.label}
                          </label>
                        ))}
                      </fieldset>
                      <label className="hl-comment">
                        <span>Comment</span>
                        <textarea
                          rows={3}
                          maxLength={2000}
                          value={editing.comment}
                          onChange={(e) => setEditing({ ...editing, comment: e.target.value })}
                        />
                      </label>
                      <div className="note-actions">
                        <button type="button" className="btn-primary" style={{ width: "auto" }} onClick={saveEdit}>
                          Save
                        </button>
                        <button type="button" className="btn-secondary" onClick={() => setEditing(null)}>
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <>
                      {h.comment && <p className="note-comment">{h.comment}</p>}
                      <div className="note-actions">
                        <Link
                          to={`/read/${bookId}?ms=${h.micro_session_id}&h=${h.id}`}
                          className="btn-secondary"
                          onClick={() => logEvent("highlight_jump", { bookId: numericBookId })}
                        >
                          Go to passage
                        </Link>
                        <button
                          type="button"
                          className="btn-secondary"
                          onClick={() => {
                            setConfirmingId(null);
                            setEditing({ id: h.id, color: h.color, comment: h.comment || "" });
                          }}
                        >
                          Edit
                        </button>
                        {book && (
                          <button
                            type="button"
                            className="btn-secondary"
                            aria-expanded={citingId === h.id}
                            onClick={() => setCitingId(citingId === h.id ? null : h.id)}
                          >
                            Cite
                          </button>
                        )}
                        {confirmingId === h.id ? (
                          <>
                            <button type="button" className="btn-secondary hl-danger" onClick={() => remove(h.id)}>
                              Confirm delete
                            </button>
                            <button type="button" className="btn-secondary" onClick={() => setConfirmingId(null)}>
                              Keep
                            </button>
                          </>
                        ) : (
                          <button type="button" className="btn-secondary" onClick={() => setConfirmingId(h.id)}>
                            Delete
                          </button>
                        )}
                      </div>
                      {book && citingId === h.id && <CiteControl book={book} highlight={h} bookId={numericBookId} />}
                    </>
                  )}
                </article>
              ))}
            </section>
          ))}
        </>
      )}
    </div>
  );
}
