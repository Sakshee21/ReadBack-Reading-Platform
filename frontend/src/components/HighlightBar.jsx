import { forwardRef, useState } from "react";
import { HIGHLIGHT_COLORS, MAX_COMMENT } from "../highlights/constants";

/**
 * The bar fixed to the bottom of the screen for creating or editing a
 * highlight. In create mode, picking a colour saves (the comment box is
 * optional); in edit mode a colour change saves at once and the comment has
 * its own Save button.
 */
const HighlightBar = forwardRef(function HighlightBar(
  { mode, quote, initialColor, initialComment = "", error, busy, onPickColor, onSaveComment, onDelete, onClose, extra = null },
  ref
) {
  const [comment, setComment] = useState(initialComment || "");
  const [confirming, setConfirming] = useState(false);
  const editing = mode === "edit";

  return (
    <div
      ref={ref}
      className="hl-bar"
      role="group"
      aria-label="Highlight"
      tabIndex={-1}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.stopPropagation();
          onClose();
        }
      }}
    >
      {editing && quote && (
        <p className="hl-bar-quote">
          &ldquo;{quote.length > 120 ? `${quote.slice(0, 120)}…` : quote}&rdquo;
        </p>
      )}
      <div className="hl-colors">
        {HIGHLIGHT_COLORS.map((c) => (
          <button
            key={c.id}
            type="button"
            className="hl-color"
            aria-pressed={editing ? initialColor === c.id : undefined}
            disabled={busy}
            onClick={() => onPickColor(c.id, comment)}
          >
            <span className="hl-dot" style={{ background: c.hue }} aria-hidden="true" />
            {c.label}
          </button>
        ))}
      </div>
      {editing && extra}
      <label className="hl-comment">
        <span>Comment (optional)</span>
        <textarea
          rows={2}
          maxLength={MAX_COMMENT}
          value={comment}
          onChange={(e) => setComment(e.target.value)}
        />
      </label>
      {!editing && <p className="hl-hint">Pick a colour to save the highlight.</p>}
      {error && (
        <p className="hl-error" role="alert">
          {error}
        </p>
      )}
      <div className="hl-actions">
        {editing && (
          <button
            type="button"
            className="btn-primary"
            style={{ width: "auto" }}
            disabled={busy}
            onClick={() => onSaveComment(comment)}
          >
            Save comment
          </button>
        )}
        {editing &&
          (confirming ? (
            <button type="button" className="btn-secondary hl-danger" disabled={busy} onClick={onDelete}>
              Confirm delete
            </button>
          ) : (
            <button type="button" className="btn-secondary" disabled={busy} onClick={() => setConfirming(true)}>
              Delete
            </button>
          ))}
        <button type="button" className="btn-secondary" onClick={onClose}>
          {editing ? "Close" : "Cancel"}
        </button>
      </div>
    </div>
  );
});

export default HighlightBar;
