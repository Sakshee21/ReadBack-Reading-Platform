import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, logEvent } from "../api";
import UploadBookDialog from "../components/UploadBookDialog";
import { useAuth } from "../AuthContext";
import StreakDisplay from "../components/StreakDisplay";
import NudgeBanner from "../components/NudgeBanner";
import SettingsPanel from "../components/SettingsPanel";
import Icon from "../components/Icon";

export default function Library() {
  const { logout } = useAuth();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [books, setBooks] = useState([]);
  const [progressByBook, setProgressByBook] = useState({});
  const [streak, setStreak] = useState(null);
  const [nudge, setNudge] = useState(null);
  const [loading, setLoading] = useState(true);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(null);

  const loadBooks = useCallback(async () => {
    const bookList = await api.listBooks();
    setBooks(bookList);
    const entries = await Promise.all(
      // a book still converting has no progress row yet
      bookList.map((book) =>
        api
          .getProgress(book.id)
          .then((p) => [book.id, p])
          .catch(() => [book.id, null])
      )
    );
    setProgressByBook(Object.fromEntries(entries));
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const [streakData, nudgeData] = await Promise.all([
        api.getStreak(),
        api.getNudge().catch(() => null),
      ]);
      if (cancelled) return;
      setStreak(streakData);
      setNudge(nudgeData);
      await loadBooks();
      if (cancelled) return;
      setLoading(false);
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [loadBooks]);

  async function handleDelete(book) {
    setConfirmDelete(null);
    try {
      await api.deleteBook(book.id);
      logEvent("book_deleted", { bookId: book.id, source_type: book.source_type });
      await loadBooks();
    } catch {
      // the list reload below will show the book still there
      await loadBooks();
    }
  }

  if (loading) return <div className="page-loading">Loading your library...</div>;

  return (
    <div className="library-page">
      <div className="library-header">
        <h1>Your library</h1>
        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
          <StreakDisplay streak={streak} />
          <button className="btn-secondary" onClick={() => setUploadOpen(true)}>
            <Icon name="upload" />
            Add your own book
          </button>
          <button className="btn-secondary" onClick={() => setSettingsOpen(true)}>
            <Icon name="settings" />
            Settings
          </button>
          <button className="btn-secondary" onClick={logout}>
            <Icon name="logout" />
            Log out
          </button>
        </div>
      </div>

      <NudgeBanner nudge={nudge} onDismiss={() => setNudge(null)} />

      <div className="book-grid">
        {books.map((book) => {
          const progress = progressByBook[book.id];
          const pct = progress ? progress.progress_pct : 0;
          const ready = book.status === "ready";

          const inner = (
            <>
              {book.is_user_uploaded && <span className="upload-badge">Your upload</span>}
              <h3>{book.title}</h3>
              <p className="author">{book.author}</p>
              {ready ? (
                <>
                  <div className="progress-bar">
                    <div className="fill" style={{ width: `${Math.min(pct, 100)}%` }} />
                  </div>
                  <div className="progress-label">
                    {pct > 0 ? `${pct.toFixed(0)}% read` : `${book.chapter_count} chapters`}
                  </div>
                </>
              ) : (
                <div className={`book-state ${book.status}`}>
                  {book.status === "processing"
                    ? "Converting…"
                    : book.failure_reason || "Conversion failed"}
                </div>
              )}
            </>
          );

          return (
            <div key={book.id} className="book-card-wrap">
              {ready ? (
                <Link to={`/read/${book.id}`} className="book-card">
                  {inner}
                </Link>
              ) : (
                <div className="book-card is-unavailable">{inner}</div>
              )}
              {book.is_user_uploaded && (
                <button
                  className="book-delete"
                  onClick={() => setConfirmDelete(book)}
                  aria-label={`Delete ${book.title}`}
                >
                  Delete
                </button>
              )}
            </div>
          );
        })}
      </div>

      {confirmDelete && (
        <div className="modal-overlay" onClick={() => setConfirmDelete(null)}>
          <div className="checkpoint-card" onClick={(e) => e.stopPropagation()}>
            <h2>Delete “{confirmDelete.title}”?</h2>
            <p className="subtitle">
              This removes the book, its chapters and your reading progress for it. It cannot be
              undone.
            </p>
            <button className="btn-primary" onClick={() => handleDelete(confirmDelete)}>
              Delete book
            </button>
            <button
              className="btn-secondary"
              style={{ width: "100%", marginTop: "0.6rem" }}
              onClick={() => setConfirmDelete(null)}
            >
              Keep it
            </button>
          </div>
        </div>
      )}

      <UploadBookDialog
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onAdded={loadBooks}
      />

      <SettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}
