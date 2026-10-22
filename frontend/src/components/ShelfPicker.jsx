import { useEffect, useRef, useState } from "react";
import { ALL, UNSHELVED } from "../shelves/useShelves";

/**
 * The row of shelves above the book grid.
 *
 * Chips rather than tabs, because selecting one filters the grid in place
 * instead of swapping a panel - and because "Group by shelf" shows them all
 * at once, which a tab list cannot describe.
 */
export default function ShelfPicker({
  shelves,
  selection,
  onSelect,
  grouped,
  onToggleGrouped,
  counts,
  onCreate,
  onRename,
  onDelete,
  busy = false,
}) {
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [editing, setEditing] = useState(null); // shelf id being renamed
  const [editName, setEditName] = useState("");
  const [confirming, setConfirming] = useState(null); // shelf pending deletion
  const newInput = useRef(null);
  const editInput = useRef(null);
  const addButton = useRef(null);

  useEffect(() => {
    if (adding) newInput.current?.focus();
  }, [adding]);
  useEffect(() => {
    if (editing != null) editInput.current?.select();
  }, [editing]);

  async function submitNew(event) {
    event.preventDefault();
    const wanted = name.trim();
    if (!wanted) return;
    const shelf = await onCreate(wanted);
    if (shelf) {
      setName("");
      setAdding(false);
      addButton.current?.focus();
      onSelect(shelf.id);
    }
  }

  async function submitRename(event, shelf) {
    event.preventDefault();
    const wanted = editName.trim();
    if (!wanted || wanted === shelf.name) {
      setEditing(null);
      return;
    }
    if (await onRename(shelf.id, wanted)) setEditing(null);
  }

  return (
    <div className="shelf-bar">
      <div className="shelf-chips" role="group" aria-label="Shelves">
        <Chip
          label="All books"
          count={counts.all}
          active={selection === ALL && !grouped}
          onClick={() => onSelect(ALL)}
        />
        {shelves.map((shelf) =>
          editing === shelf.id ? (
            <form key={shelf.id} className="shelf-rename" onSubmit={(e) => submitRename(e, shelf)}>
              <label className="sr-only" htmlFor={`rename-${shelf.id}`}>
                Rename shelf {shelf.name}
              </label>
              <input
                id={`rename-${shelf.id}`}
                ref={editInput}
                value={editName}
                maxLength={40}
                disabled={busy}
                onChange={(e) => setEditName(e.target.value)}
                onKeyDown={(e) => e.key === "Escape" && setEditing(null)}
              />
              <button type="submit" className="btn-secondary" disabled={busy}>
                Save
              </button>
              <button type="button" className="btn-secondary" onClick={() => setEditing(null)}>
                Cancel
              </button>
            </form>
          ) : (
            <span key={shelf.id} className="shelf-chip-wrap">
              <Chip
                label={shelf.name}
                count={shelf.book_count}
                active={selection === shelf.id && !grouped}
                onClick={() => onSelect(shelf.id)}
              />
              <button
                type="button"
                className="shelf-edit"
                aria-label={`Rename shelf ${shelf.name}`}
                onClick={() => {
                  setEditName(shelf.name);
                  setEditing(shelf.id);
                }}
              >
                Rename
              </button>
              <button
                type="button"
                className="shelf-edit"
                aria-label={`Delete shelf ${shelf.name}`}
                onClick={() => setConfirming(shelf)}
              >
                Delete
              </button>
            </span>
          )
        )}
        <Chip
          label="Unshelved"
          count={counts.unshelved}
          active={selection === UNSHELVED && !grouped}
          onClick={() => onSelect(UNSHELVED)}
        />
      </div>

      <div className="shelf-actions">
        {adding ? (
          <form className="shelf-new" onSubmit={submitNew}>
            <label className="sr-only" htmlFor="new-shelf-name">
              Name for the new shelf
            </label>
            <input
              id="new-shelf-name"
              ref={newInput}
              value={name}
              maxLength={40}
              placeholder="Crime, To read&hellip;"
              disabled={busy}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") {
                  setAdding(false);
                  addButton.current?.focus();
                }
              }}
            />
            <button type="submit" className="btn-secondary" disabled={busy || !name.trim()}>
              Create
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => {
                setAdding(false);
                addButton.current?.focus();
              }}
            >
              Cancel
            </button>
          </form>
        ) : (
          <button
            type="button"
            ref={addButton}
            className="btn-secondary"
            onClick={() => setAdding(true)}
          >
            New shelf
          </button>
        )}

        <label className="shelf-group-toggle">
          <input
            type="checkbox"
            checked={grouped}
            onChange={(e) => onToggleGrouped(e.target.checked)}
          />
          Group by shelf
        </label>
      </div>

      {confirming && (
        <div className="modal-overlay" onClick={() => setConfirming(null)}>
          <div className="checkpoint-card" onClick={(e) => e.stopPropagation()}>
            <h2>Delete the shelf &ldquo;{confirming.name}&rdquo;?</h2>
            <p className="subtitle">
              The shelf goes; the {confirming.book_count}{" "}
              {confirming.book_count === 1 ? "book" : "books"} on it stay in your library.
            </p>
            <button
              className="btn-primary"
              onClick={async () => {
                if (await onDelete(confirming.id)) {
                  if (selection === confirming.id) onSelect(ALL);
                  setConfirming(null);
                }
              }}
            >
              Delete shelf
            </button>
            <button
              className="btn-secondary"
              style={{ width: "100%", marginTop: "0.6rem" }}
              onClick={() => setConfirming(null)}
            >
              Keep it
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Chip({ label, count, active, onClick }) {
  return (
    <button
      type="button"
      className={`shelf-chip${active ? " is-active" : ""}`}
      aria-pressed={active}
      onClick={onClick}
    >
      {label}
      <span className="shelf-chip-count">{count}</span>
    </button>
  );
}
