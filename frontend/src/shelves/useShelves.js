import { useCallback, useEffect, useState } from "react";
import { api } from "../api";

/**
 * The reader's shelves, and the operations on them.
 *
 * Every mutation returns the shelf the server built, so the list here is
 * always what the server has rather than a guess that might drift. Failures
 * surface as a message and leave the previous list alone: a shelf that will
 * not rename must not take the library down with it.
 */
export function useShelves() {
  const [shelves, setShelves] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setShelves(await api.listShelves());
      setError("");
    } catch {
      // Deliberately not the raw message: a load failure is a network or
      // server problem, and "down" or "Failed to fetch" tells the reader
      // nothing they can act on. A failed *mutation* is different - there the
      // server says why, and that is worth passing on.
      setError("Could not load your shelves. The rest of your library still works.");
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    load().then(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [load]);

  /** Replace one shelf in place, keeping the order the server gave. */
  const merge = useCallback((shelf) => {
    setShelves((all) => all.map((s) => (s.id === shelf.id ? shelf : s)));
  }, []);

  /** Run an operation, turning a failure into a message rather than a throw.
   * Returns the result, or undefined when it failed. */
  const attempt = useCallback(async (run, fallbackMessage) => {
    try {
      setError("");
      return await run();
    } catch (err) {
      setError(err.message || fallbackMessage);
      return undefined;
    }
  }, []);

  const create = useCallback(
    (name) =>
      attempt(async () => {
        const shelf = await api.createShelf(name);
        setShelves((all) => [...all, shelf]);
        return shelf;
      }, "Could not create that shelf."),
    [attempt]
  );

  const rename = useCallback(
    (id, name) =>
      attempt(async () => {
        const shelf = await api.renameShelf(id, name);
        merge(shelf);
        return shelf;
      }, "Could not rename that shelf."),
    [attempt, merge]
  );

  const remove = useCallback(
    (id) =>
      attempt(async () => {
        await api.deleteShelf(id);
        setShelves((all) => all.filter((s) => s.id !== id));
        return true;
      }, "Could not delete that shelf."),
    [attempt]
  );

  const addBook = useCallback(
    (shelfId, bookId) =>
      attempt(async () => {
        merge(await api.addBookToShelf(shelfId, bookId));
        return true;
      }, "Could not add that book to the shelf."),
    [attempt, merge]
  );

  const removeBook = useCallback(
    (shelfId, bookId) =>
      attempt(async () => {
        merge(await api.removeBookFromShelf(shelfId, bookId));
        return true;
      }, "Could not take that book off the shelf."),
    [attempt, merge]
  );

  return {
    shelves,
    loading,
    error,
    setError,
    reload: load,
    create,
    rename,
    remove,
    addBook,
    removeBook,
  };
}

export const ALL = "all";
export const UNSHELVED = "unshelved";

/** Book ids that are on at least one shelf. */
export function shelvedIds(shelves) {
  const ids = new Set();
  for (const shelf of shelves) for (const id of shelf.book_ids) ids.add(id);
  return ids;
}

/**
 * The books to show for the current selection, in the shelf's own order when
 * a shelf is selected and in library order otherwise.
 */
export function booksFor(selection, books, shelves) {
  if (selection === ALL) return books;
  if (selection === UNSHELVED) {
    const shelved = shelvedIds(shelves);
    return books.filter((book) => !shelved.has(book.id));
  }
  const shelf = shelves.find((s) => s.id === selection);
  if (!shelf) return books;
  const byId = new Map(books.map((book) => [book.id, book]));
  return shelf.book_ids.map((id) => byId.get(id)).filter(Boolean);
}
