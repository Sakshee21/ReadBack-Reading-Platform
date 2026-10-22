import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, logEvent } from "../api";
import UploadBookDialog from "../components/UploadBookDialog";
import { useAuth } from "../AuthContext";
import StreakDisplay from "../components/StreakDisplay";
import NudgeBanner from "../components/NudgeBanner";
import SettingsPanel from "../components/SettingsPanel";
import Icon from "../components/Icon";
import ShelfPicker from "../components/ShelfPicker";
import ShelfMenu from "../components/ShelfMenu";
import { ALL, UNSHELVED, booksFor, shelvedIds, useShelves } from "../shelves/useShelves";

// What the reader last had open, so the library comes back as they left it.
const VIEW_KEY = "readback_shelf_view";

function readView(userId) {
  try {
    const all = JSON.parse(localStorage.getItem(VIEW_KEY) || "{}");
    const mine = all[String(userId)] || {};
    return {
      selection: mine.selection ?? ALL,
      grouped: Boolean(mine.grouped),
    };
  } catch {
    return { selection: ALL, grouped: false };
  }
}

function writeView(userId, view) {
  try {
    const all = JSON.parse(localStorage.getItem(VIEW_KEY) || "{}");
    all[String(userId)] = view;
    localStorage.setItem(VIEW_KEY, JSON.stringify(all));
  } catch {
    // A reader with storage blocked simply starts on "All books" each time.
  }
}

export default function Library() {
  const { logout, user } = useAuth();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [books, setBooks] = useState([]);
  const [progressByBook, setProgressByBook] = useState({});
  const [streak, setStreak] = useState(null);
  const [nudge, setNudge] = useState(null);
  const [loading, setLoading] = useState(true);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(null);

  const shelving = useShelves();
  const userKey = user?.id ?? "anon";
  const [selection, setSelection] = useState(ALL);
  const [grouped, setGrouped] = useState(false);

  // Restore the last view once the user is known.
  useEffect(() => {
    const view = readView(userKey);
    setSelection(view.selection);
    setGrouped(view.grouped);
  }, [userKey]);

  const chooseShelf = useCallback(
    (next) => {
      setSelection(next);
      setGrouped(false);
      writeView(userKey, { selection: next, grouped: false });
    },
    [userKey]
  );

  const chooseGrouped = useCallback(
    (next) => {
      setGrouped(next);
      writeView(userKey, { selection, grouped: next });
    },
    [selection, userKey]
  );

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

  const unshelvedCount = (() => {
    const shelved = shelvedIds(shelving.shelves);
    return books.filter((book) => !shelved.has(book.id)).length;
  })();
  const shown = booksFor(selection, books, shelving.shelves);
  const cardProps = {
    progressByBook,
    shelves: shelving.shelves,
    onAddToShelf: shelving.addBook,
    onRemoveFromShelf: shelving.removeBook,
    onCreateShelf: shelving.create,
    onDelete: setConfirmDelete,
  };

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
          <Link to="/research" className="btn-secondary">
            <Icon name="research" />
            Research
          </Link>
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

      <ShelfPicker
        shelves={shelving.shelves}
        selection={selection}
        onSelect={chooseShelf}
        grouped={grouped}
        onToggleGrouped={chooseGrouped}
        counts={{ all: books.length, unshelved: unshelvedCount }}
        onCreate={shelving.create}
        onRename={shelving.rename}
        onDelete={shelving.remove}
        busy={shelving.loading}
      />

      {shelving.error && (
        <p className="form-error" role="alert">
          {shelving.error}
        </p>
      )}

      {grouped ? (
        <div className="shelf-groups">
          {shelving.shelves.length === 0 && (
            <p className="notes-empty">
              No shelves yet. Make one above to group your library.
            </p>
          )}
          {shelving.shelves.map((shelf) => (
            <section key={shelf.id} className="shelf-group">
              <h2>
                {shelf.name} <span className="shelf-chip-count">{shelf.book_count}</span>
              </h2>
              {shelf.book_count === 0 ? (
                <p className="notes-empty">No books on this shelf yet.</p>
              ) : (
                <div className="book-grid">
                  {booksFor(shelf.id, books, shelving.shelves).map((book) => (
                    <BookCard key={book.id} book={book} {...cardProps} />
                  ))}
                </div>
              )}
            </section>
          ))}

          {unshelvedCount > 0 && (
            <section className="shelf-group">
              <h2>
                Unshelved <span className="shelf-chip-count">{unshelvedCount}</span>
              </h2>
              <div className="book-grid">
                {booksFor(UNSHELVED, books, shelving.shelves).map((book) => (
                  <BookCard key={book.id} book={book} {...cardProps} />
                ))}
              </div>
            </section>
          )}
        </div>
      ) : shown.length === 0 ? (
        <p className="notes-empty">
          {selection === ALL
            ? "No books in your library yet."
            : selection === UNSHELVED
              ? "Every book is on a shelf."
              : "No books on this shelf yet. Use the Shelves button on a book to add one."}
        </p>
      ) : (
        <div className="book-grid">
          {shown.map((book) => (
            <BookCard key={book.id} book={book} {...cardProps} />
          ))}
        </div>
      )}

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

/**
 * One book in the grid. Lifted out of the page unchanged in substance, so the
 * flat view and the grouped view draw the same card rather than two that
 * drift apart.
 */
function BookCard({
  book,
  progressByBook,
  shelves,
  onAddToShelf,
  onRemoveFromShelf,
  onCreateShelf,
  onDelete,
}) {
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
          {book.status === "processing" ? "Converting…" : book.failure_reason || "Conversion failed"}
        </div>
      )}
    </>
  );

  return (
    <div className="book-card-wrap">
      {ready ? (
        <Link to={`/read/${book.id}`} className="book-card">
          {inner}
        </Link>
      ) : (
        <div className="book-card is-unavailable">{inner}</div>
      )}
      {ready && (
        <Link
          to={`/books/${book.id}/notes`}
          className={`book-notes${book.is_user_uploaded ? " has-delete" : ""}`}
          aria-label={`Notes for ${book.title}`}
        >
          Notes
        </Link>
      )}
      {ready && (
        <ShelfMenu
          book={book}
          shelves={shelves}
          onAdd={onAddToShelf}
          onRemove={onRemoveFromShelf}
          onCreate={onCreateShelf}
        />
      )}
      {book.is_user_uploaded && (
        <button
          className="book-delete"
          onClick={() => onDelete(book)}
          aria-label={`Delete ${book.title}`}
        >
          Delete
        </button>
      )}
    </div>
  );
}
