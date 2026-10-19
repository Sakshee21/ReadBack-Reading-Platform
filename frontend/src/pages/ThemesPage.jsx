import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, logEvent } from "../api";

/**
 * The themes the reader has met so far, and the passages for each. The server
 * only returns tags for passages already reached, so nothing here can spoil the
 * rest of the book.
 */
export default function ThemesPage() {
  const { bookId } = useParams();
  const numericBookId = Number(bookId);
  const [data, setData] = useState(null);
  const [book, setBook] = useState(null);
  const [status, setStatus] = useState("loading"); // loading | ready | failed
  const [selected, setSelected] = useState(null);
  const [passages, setPassages] = useState([]);
  const [passagesFailed, setPassagesFailed] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [consentError, setConsentError] = useState("");
  const openedLogged = useRef(false);
  const passageRequest = useRef(0); // only the latest request may set the passages

  useEffect(() => {
    let current = true;
    passageRequest.current += 1;
    setSelected(null);
    setPassages([]);
    async function load() {
      try {
        const [themes, books] = await Promise.all([api.getThemes(bookId), api.listBooks()]);
        if (!current) return;
        setData(themes);
        setBook(books.find((b) => b.id === numericBookId) || null);
        setStatus("ready");
        if (!openedLogged.current) {
          openedLogged.current = true;
          logEvent("themes_opened", { bookId: numericBookId, count: themes.themes.length });
          if (themes.tagging.pending || themes.tagging.failed) {
            logEvent("theme_tagging_status", { bookId: numericBookId, ...themes.tagging });
          }
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

  async function choose(theme) {
    const mine = ++passageRequest.current;
    setSelected(theme);
    setPassages([]);
    setPassagesFailed(false);
    logEvent("theme_filter_selected", { bookId: numericBookId, theme });
    try {
      const rows = await api.getThemePassages(bookId, theme);
      if (mine === passageRequest.current) setPassages(rows);
    } catch {
      if (mine === passageRequest.current) setPassagesFailed(true);
    }
  }

  async function changeConsent(granted) {
    setConsentError("");
    try {
      const result = await api.setThemeConsent(bookId, granted);
      setBook((b) => ({ ...b, theme_tagging_consent: result.theme_tagging_consent }));
      setConfirming(false);
      logEvent("theme_consent_changed", { bookId: numericBookId, granted: result.theme_tagging_consent });
      if (!granted) {
        passageRequest.current += 1; // drop any answer still on its way
        setData((d) => ({ ...d, themes: [], tagging: { tagged: 0, pending: 0, failed: 0 } }));
        setSelected(null);
        setPassages([]);
      }
    } catch {
      setConsentError("Could not change that setting. Try again.");
    }
  }

  if (status === "loading") return <div className="page-loading">Loading themes...</div>;
  if (status === "failed") {
    return (
      <div className="themes-page">
        <p role="alert">Could not load themes. Try again in a moment.</p>
        <Link to="/library">Library</Link>
      </div>
    );
  }

  const isOwnUpload = Boolean(book?.is_user_uploaded);
  const preparing = data.tagging.pending > 0;

  return (
    <div className="themes-page">
      <div className="notes-header">
        <h1>Themes{book?.title ? `: ${book.title}` : ""}</h1>
        <nav className="notes-nav">
          <Link to={`/read/${bookId}`} className="btn-secondary">
            Back to reading
          </Link>{" "}
          <Link to={`/books/${bookId}/notes`} className="btn-secondary">
            Notes
          </Link>{" "}
          <Link to="/library" className="btn-secondary">
            Library
          </Link>
        </nav>
      </div>

      <p className="themes-note">
        Themes are labelled by an AI model and can be wrong, so treat them as a guide. Only passages
        you have reached are shown, so nothing here spoils what comes next.
      </p>

      {isOwnUpload && (
        <div className="themes-consent">
          {book.theme_tagging_consent ? (
            confirming ? (
              <>
                <p>
                  Withdrawing stops tagging and deletes this book's theme tags. Text already sent to
                  the AI service cannot be taken back.
                </p>
                <button type="button" className="btn-secondary hl-danger" onClick={() => changeConsent(false)}>
                  Yes, withdraw
                </button>{" "}
                <button type="button" className="btn-secondary" onClick={() => setConfirming(false)}>
                  Keep tagging
                </button>
              </>
            ) : (
              <button type="button" className="btn-secondary" onClick={() => setConfirming(true)}>
                Withdraw theme tagging
              </button>
            )
          ) : (
            <button type="button" className="btn-secondary" onClick={() => changeConsent(true)}>
              Allow theme tagging
            </button>
          )}
          {consentError && (
            <p role="alert" className="hl-error">
              {consentError}
            </p>
          )}
        </div>
      )}

      {preparing && <p className="themes-note">Some passages are still being prepared. Check back soon.</p>}

      {data.themes.length === 0 ? (
        <p className="notes-empty">
          {isOwnUpload && !book.theme_tagging_consent
            ? "Theme tagging is off for this book."
            : "There are no theme tags for the passages you have read yet."}
        </p>
      ) : (
        <>
          <fieldset className="notes-filter themes-list">
            <legend>Theme</legend>
            {data.themes.map((t) => (
              <label key={t.theme}>
                <input
                  type="radio"
                  name="theme"
                  checked={selected === t.theme}
                  onChange={() => choose(t.theme)}
                />{" "}
                {t.label} ({t.count})
              </label>
            ))}
          </fieldset>

          {!selected && <p className="notes-empty">Choose a theme to see where it appears.</p>}
          <div aria-live="polite">
          {selected && (
            <h2 className="themes-results-heading">
              Passages for {data.themes.find((t) => t.theme === selected)?.label || selected}
            </h2>
          )}
          {passagesFailed && (
            <p role="alert" className="hl-error">
              Could not load those passages.
            </p>
          )}
          {passages.map((p) => (
            <article key={p.micro_session_id} className="note-card">
              <div className="note-meta">
                <span>{p.chapter_title || `Chapter ${p.chapter_index}`}</span>
                {p.session_number && <span>Session {p.session_number}</span>}
              </div>
              <p className="note-quote">{p.preview}</p>
              <ul className="theme-chips" aria-label="Themes in this passage">
                {p.themes.map((t) => (
                  <li key={t.theme} className="theme-chip">
                    {t.label}
                  </li>
                ))}
              </ul>
              <div className="note-actions">
                <Link
                  to={`/read/${bookId}?ms=${p.micro_session_id}`}
                  className="btn-secondary"
                  onClick={() => logEvent("theme_passage_opened", { bookId: numericBookId, theme: selected })}
                >
                  Go to passage
                </Link>
              </div>
            </article>
          ))}
          </div>
        </>
      )}
    </div>
  );
}
