import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { api, logEvent } from "../api";
import { HIGHLIGHT_COLORS, colorLabel } from "../highlights/constants";
import { isStale, paragraphStarts, selectionToRange, splitSegments } from "../highlights/positions";
import { edgeScrollStep, usableBottom } from "../highlights/selectionScroll";
import HighlightBar from "./HighlightBar";
import CiteControl from "./CiteControl";

const OVERLAP_MESSAGE = "That overlaps an existing highlight. Select it to edit instead.";
const SAVE_FAILED = "Could not save that highlight. Try again.";

const BAR_HEIGHT_VAR = "--hl-bar-height";

/**
 * Publish the bar height that the passage padding is sized from - but only
 * when it has actually changed.
 *
 * Writing it unconditionally looks harmless and is not. The padding it drives
 * is part of the document height, so clearing it shrinks the page, the
 * browser clamps the scroll position upward to fit, and putting the value
 * back does not restore where the reader was. Doing that on every selection
 * change - which is what a drag produces, many times a second - makes the
 * page jump up and down under the pointer.
 */
function publishBarHeight(bar, published) {
  const root = document.documentElement;
  if (!bar) {
    if (published.current !== null) {
      root.style.removeProperty(BAR_HEIGHT_VAR);
      published.current = null;
    }
    return;
  }
  const height = Math.ceil(bar.getBoundingClientRect().height);
  if (height !== published.current) {
    root.style.setProperty(BAR_HEIGHT_VAR, `${height}px`);
    published.current = height;
  }
}

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
  book = null,
  // Passed straight to CiteControl. The research reader supplies journal and
  // textbook-chapter formats and its own passage link; books use the defaults.
  cite,
  linkTo,
}) {
  const textRef = useRef(null);
  const barRef = useRef(null);
  const focusedRef = useRef(null);
  const [pending, setPending] = useState(null); // {start, end}
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // The bar height this passage has published, so it can tell a real change
  // from a re-render and leave the page height alone on the latter.
  const publishedBarHeight = useRef(null);

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

  // Dragging a selection towards the bar scrolls the page instead of stopping
  // at it. Without this the reader cannot select anything the bar covers: the
  // pointer never reaches the bottom of the window, so the browser never
  // starts its own auto-scroll.
  useEffect(() => {
    const container = textRef.current;
    if (!enabled || !container) return undefined;

    let frame = 0;
    let pointerY = null;

    const step = () => {
      frame = 0;
      if (pointerY == null) return;
      // Dragged below the window, the browser does its own auto-scroll.
      // Adding ours on top of it would scroll at double speed and overshoot.
      if (pointerY > window.innerHeight) {
        frame = requestAnimationFrame(step);
        return;
      }
      const barHeight = barRef.current?.getBoundingClientRect().height ?? 0;
      const amount = edgeScrollStep(pointerY, {
        bottom: usableBottom(window.innerHeight, barHeight),
      });
      if (amount) {
        // jsdom and older browsers do not implement scrollBy; a reader who
        // cannot auto-scroll is no worse off than before this existed.
        try {
          window.scrollBy(0, amount);
        } catch {
          pointerY = null;
          return;
        }
      }
      frame = requestAnimationFrame(step);
    };

    const start = (e) => {
      if (e.button !== 0) return; // left button / touch only
      pointerY = e.clientY;
      // An attribute on the body, not React state. Re-rendering mid-drag can
      // replace the very text nodes the live selection points into, which
      // drops the selection the reader is in the middle of making - so the
      // one thing this must not do is cause a render.
      document.body.dataset.hlSelecting = "true";
      if (!frame) frame = requestAnimationFrame(step);
    };
    const move = (e) => {
      if (pointerY != null) pointerY = e.clientY;
    };
    const stop = () => {
      pointerY = null;
      delete document.body.dataset.hlSelecting;
      if (frame) cancelAnimationFrame(frame);
      frame = 0;
    };

    container.addEventListener("pointerdown", start);
    // On window, not the container: a drag normally ends outside the text.
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
    return () => {
      container.removeEventListener("pointerdown", start);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
      if (frame) cancelAnimationFrame(frame);
      delete document.body.dataset.hlSelecting;
    };
  }, [enabled]);

  // The bar is as tall as its contents, so the room left for the passage
  // underneath is measured rather than guessed. Runs after every render but
  // only writes on a real change, and before paint, so the measurement and
  // the padding it drives land together.
  useLayoutEffect(() => {
    publishBarHeight(barRef.current, publishedBarHeight);
  });

  // The bar can rewrap without React rendering anything, so re-measure on a
  // resize; and let go of the variable when the passage goes away.
  useEffect(() => {
    const onResize = () => publishBarHeight(barRef.current, publishedBarHeight);
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      publishBarHeight(null, publishedBarHeight);
    };
  }, []);

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
          extra={
            editing && book ? (
              <CiteControl
                book={book}
                highlight={editing}
                bookId={bookId}
                {...(cite ? { cite } : {})}
                {...(linkTo ? { linkTo } : {})}
              />
            ) : null
          }
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
