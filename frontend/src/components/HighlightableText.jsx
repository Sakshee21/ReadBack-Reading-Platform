import { useEffect, useMemo, useRef, useState } from "react";
import { api, logEvent } from "../api";
import { HIGHLIGHT_COLORS, colorLabel } from "../highlights/constants";
import { isStale, paragraphStarts, selectionToRange, splitSegments } from "../highlights/positions";
import HighlightBar from "./HighlightBar";

const OVERLAP_MESSAGE = "That overlaps an existing highlight. Select it to edit instead.";
const SAVE_FAILED = "Could not save that highlight. Try again.";

const byStart = (a, b) => a.start - b.start;
const hueOf = (id) => HIGHLIGHT_COLORS.find((c) => c.id === id)?.hue;

/**
 * The passage text, with the reader's highlights drawn in and, when enabled,
 * a bar to create or edit them. Positions are Unicode code points into `text`.
 */
export default function HighlightableText({
  text,
  bookId,
  microSessionId,
  enabled,
  highlights,
  onChanged,
  focusHighlightId = null,
  onFocused,
}) {
  const textRef = useRef(null);
  const barRef = useRef(null);
  const focusedRef = useRef(null);
  const [pending, setPending] = useState(null); // {start, end}
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const paragraphs = useMemo(() => paragraphStarts(text), [text]);
  const editing = editingId == null ? null : highlights.find((h) => h.id === editingId) || null;
  const logCtx = { bookId, microSessionId };

  // A different passage, or highlighting being switched off, closes the bar.
  useEffect(() => {
    setPending(null);
    setEditingId(null);
    setError("");
  }, [text, enabled]);

  // The listeners read the latest state through refs, so they are registered
  // once per passage instead of on every selection change.
  const latest = useRef({});
  latest.current = { pending, editing, closeBar };

  useEffect(() => {
    if (!enabled) return undefined;
    const onSelectionChange = () => {
      const container = textRef.current;
      const selection = window.getSelection();
      // A collapsed selection (tapping the bar, the comment box) changes nothing.
      if (!container || !selection || !selection.rangeCount || selection.isCollapsed) return;
      const range = selectionToRange(selection, container, text);
      if (range) {
        setPending((prev) => (prev && prev.start === range.start && prev.end === range.end ? prev : range));
        setEditingId(null);
        setError("");
      } else {
        // A real selection that is not a valid highlight here (elsewhere, across
        // passages, too long): drop any earlier range so a stale one is never saved.
        setPending(null);
      }
    };
    const onKeyDown = (e) => {
      const { pending: p, editing: ed, closeBar: close } = latest.current;
      if (!p && !ed) return;
      if (e.altKey && e.key.toLowerCase() === "h") {
        e.preventDefault();
        barRef.current?.querySelector("button")?.focus();
      } else if (e.key === "Escape") {
        close();
      }
    };
    document.addEventListener("selectionchange", onSelectionChange);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("selectionchange", onSelectionChange);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [enabled, text]);

  // Arriving from the notes page: bring the highlight into view once.
  useEffect(() => {
    if (focusHighlightId == null || focusedRef.current === focusHighlightId) return;
    const mark = textRef.current?.querySelector(`mark[data-highlight-id="${focusHighlightId}"]`);
    if (!mark) return;
    focusedRef.current = focusHighlightId;
    mark.scrollIntoView?.({ block: "center" });
    mark.focus();
    onFocused?.();
  }, [focusHighlightId, highlights, onFocused]);

  function closeBar() {
    setPending(null);
    setEditingId(null);
    setError("");
    window.getSelection()?.removeAllRanges();
    textRef.current?.focus();
  }

  async function create(color, comment) {
    if (!pending || busy) return;
    setBusy(true);
    setError("");
    const trimmed = (comment || "").trim();
    try {
      const saved = await api.createHighlight(bookId, {
        micro_session_id: microSessionId,
        start: pending.start,
        end: pending.end,
        color,
        comment: trimmed || null,
      });
      logEvent("highlight_created", {
        ...logCtx,
        color,
        length: pending.end - pending.start,
        has_comment: Boolean(trimmed),
      });
      setPending(null);
      window.getSelection()?.removeAllRanges();
      textRef.current?.focus();
      onChanged([...highlights, saved].sort(byStart));
    } catch (err) {
      setError(err?.status === 409 ? OVERLAP_MESSAGE : SAVE_FAILED);
    } finally {
      setBusy(false);
    }
  }

  async function update(patch) {
    if (!editing || busy) return;
    setBusy(true);
    setError("");
    try {
      const saved = await api.updateHighlight(editing.id, patch);
      logEvent("highlight_edited", {
        ...logCtx,
        color: saved.color,
        has_comment: Boolean(saved.comment),
      });
      onChanged(highlights.map((h) => (h.id === saved.id ? { ...h, ...saved } : h)));
    } catch {
      setError(SAVE_FAILED);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!editing || busy) return;
    setBusy(true);
    setError("");
    try {
      const id = editing.id;
      await api.deleteHighlight(id);
      logEvent("highlight_deleted", logCtx);
      setEditingId(null);
      textRef.current?.focus();
      onChanged(highlights.filter((h) => h.id !== id));
    } catch {
      setError("Could not delete that highlight. Try again.");
    } finally {
      setBusy(false);
    }
  }

  function openEditor(h) {
    if (!enabled) return;
    setPending(null);
    setError("");
    setEditingId(h.id);
  }

  const drawn = highlights.filter((h) => !isStale(text, h));
  const showBar = enabled && (pending || editing);

  return (
    <>
      <div
        ref={textRef}
        data-highlight-text
        tabIndex={-1}
        className="hl-text"
        onPointerDown={(e) => {
          if (editingId == null) setPending(null);
          else if (!e.target.closest?.("mark")) setEditingId(null); // click away closes the editor
        }}
      >
        {paragraphs.map((para) => (
          <p key={para.start} data-start={para.start}>
            {splitSegments(text, para, drawn).map((seg, i) =>
              seg.highlight ? (
                <mark
                  key={i}
                  className="hl-mark"
                  data-highlight-id={seg.highlight.id}
                  style={{ "--hl": hueOf(seg.highlight.color) }}
                  tabIndex={0}
                  role="button"
                  title={`${colorLabel(seg.highlight.color)} highlight`}
                  aria-label={`Highlight, ${colorLabel(seg.highlight.color)}: ${seg.highlight.quote.slice(0, 60)}`}
                  onClick={() => {
                    if (window.getSelection()?.isCollapsed !== false) openEditor(seg.highlight);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      openEditor(seg.highlight);
                    }
                  }}
                >
                  {seg.text}
                </mark>
              ) : (
                seg.text
              )
            )}
          </p>
        ))}
      </div>
      {showBar && (
        <HighlightBar
          key={editing ? `edit-${editing.id}` : `create-${pending.start}-${pending.end}`}
          ref={barRef}
          mode={editing ? "edit" : "create"}
          quote={editing?.quote}
          initialColor={editing?.color}
          initialComment={editing?.comment || ""}
          error={error}
          busy={busy}
          onPickColor={(color, comment) => (editing ? update({ color }) : create(color, comment))}
          onSaveComment={(comment) => update({ comment: comment.trim() || null })}
          onDelete={remove}
          onClose={closeBar}
        />
      )}
    </>
  );
}
