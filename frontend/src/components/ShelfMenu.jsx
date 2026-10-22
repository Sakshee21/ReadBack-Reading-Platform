import { useEffect, useRef, useState } from "react";

/**
 * The "Shelves" menu on a book card: a checkbox per shelf, plus a field for a
 * new one.
 *
 * Checkboxes rather than a drag target, because this has to work from the
 * keyboard and with a screen reader. Each box says what it does ("Crime,
 * holds Pride and Prejudice"), Escape closes the menu and puts focus back on
 * the button, and nothing here depends on a pointer.
 */
export default function ShelfMenu({ book, shelves, onAdd, onRemove, onCreate, busy = false }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [working, setWorking] = useState(null); // shelf id mid-flight
  const button = useRef(null);
  const panel = useRef(null);
  const newInput = useRef(null);

  // Clicking away closes the menu, as a menu should.
  useEffect(() => {
    if (!open) return undefined;
    const onDown = (event) => {
      if (panel.current?.contains(event.target) || button.current?.contains(event.target)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  function close() {
    setOpen(false);
    button.current?.focus();
  }

  async function toggle(shelf, checked) {
    setWorking(shelf.id);
    if (checked) await onAdd(shelf.id, book.id);
    else await onRemove(shelf.id, book.id);
    setWorking(null);
  }

  async function createAndAdd(event) {
    event.preventDefault();
    const wanted = name.trim();
    if (!wanted) return;
    const shelf = await onCreate(wanted);
    if (shelf) {
      await onAdd(shelf.id, book.id);
      setName("");
      newInput.current?.focus();
    }
  }

  const on = shelves.filter((shelf) => shelf.book_ids.includes(book.id));
  const summary = on.length ? `${on.length} shelf${on.length === 1 ? "" : "s"}` : "Shelves";

  return (
    <div className="shelf-menu">
      <button
        type="button"
        ref={button}
        className="book-shelves"
        aria-expanded={open}
        aria-haspopup="true"
        aria-label={
          on.length
            ? `Shelves for ${book.title}: on ${on.map((s) => s.name).join(", ")}`
            : `Shelves for ${book.title}: on none`
        }
        onClick={() => setOpen((was) => !was)}
      >
        {summary}
      </button>

      {open && (
        <div
          className="shelf-menu-panel"
          ref={panel}
          role="group"
          aria-label={`Shelves for ${book.title}`}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.stopPropagation();
              close();
            }
          }}
        >
          {shelves.length === 0 && (
            <p className="shelf-menu-empty">No shelves yet. Make one below.</p>
          )}
          <ul className="shelf-menu-list">
            {shelves.map((shelf) => {
              const checked = shelf.book_ids.includes(book.id);
              return (
                <li key={shelf.id}>
                  <label>
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={busy || working === shelf.id}
                      onChange={(e) => toggle(shelf, e.target.checked)}
                    />
                    <span>{shelf.name}</span>
                  </label>
                </li>
              );
            })}
          </ul>

          <form className="shelf-menu-new" onSubmit={createAndAdd}>
            <label className="sr-only" htmlFor={`new-shelf-for-${book.id}`}>
              New shelf for {book.title}
            </label>
            <input
              id={`new-shelf-for-${book.id}`}
              ref={newInput}
              value={name}
              maxLength={40}
              placeholder="New shelf&hellip;"
              disabled={busy}
              onChange={(e) => setName(e.target.value)}
            />
            <button type="submit" className="btn-secondary" disabled={busy || !name.trim()}>
              Add
            </button>
          </form>

          <button type="button" className="btn-secondary shelf-menu-close" onClick={close}>
            Done
          </button>
        </div>
      )}
    </div>
  );
}
