import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../AuthContext";
import StreakDisplay from "../components/StreakDisplay";

export default function Library() {
  const { logout } = useAuth();
  const [books, setBooks] = useState([]);
  const [progressByBook, setProgressByBook] = useState({});
  const [streak, setStreak] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const [bookList, streakData] = await Promise.all([api.listBooks(), api.getStreak()]);
      if (cancelled) return;
      setBooks(bookList);
      setStreak(streakData);

      const progressEntries = await Promise.all(
        bookList.map((book) => api.getProgress(book.id).then((p) => [book.id, p]))
      );
      if (cancelled) return;
      setProgressByBook(Object.fromEntries(progressEntries));
      setLoading(false);
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) return <div className="page-loading">Loading your library...</div>;

  return (
    <div className="library-page">
      <div className="library-header">
        <h1>Your library</h1>
        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
          <StreakDisplay streak={streak} />
          <button className="btn-secondary" onClick={logout}>
            Log out
          </button>
        </div>
      </div>

      <div className="book-grid">
        {books.map((book) => {
          const progress = progressByBook[book.id];
          const pct = progress ? progress.progress_pct : 0;
          return (
            <Link key={book.id} to={`/read/${book.id}`} className="book-card">
              <h3>{book.title}</h3>
              <p className="author">{book.author}</p>
              <div className="progress-bar">
                <div className="fill" style={{ width: `${Math.min(pct, 100)}%` }} />
              </div>
              <div className="progress-label">
                {pct > 0 ? `${pct.toFixed(0)}% read` : `${book.chapter_count} chapters`}
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
