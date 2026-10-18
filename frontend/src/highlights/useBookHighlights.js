import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";

/**
 * The reader's highlights for a book, reloaded whenever `reloadKey` changes
 * (the first micro-session of the block on screen). A failed load shows no
 * highlights rather than blocking the text.
 */
export function useBookHighlights(bookId, reloadKey) {
  const [highlights, setHighlights] = useState([]);
  // Counts local edits, so a response that started before one is not applied.
  const edits = useRef(0);

  useEffect(() => {
    if (reloadKey == null) return undefined;
    let current = true;
    const load = (retriesLeft) => {
      const seen = edits.current;
      api
        .listHighlights(bookId)
        .then((rows) => {
          if (!current) return;
          // Edited while loading: this answer may be missing the change, so ask again.
          if (edits.current !== seen && retriesLeft > 0) load(retriesLeft - 1);
          else setHighlights(rows);
        })
        .catch(() => current && setHighlights([]));
    };
    load(3);
    return () => {
      current = false;
    };
  }, [bookId, reloadKey]);

  const replaceForPart = useCallback((microSessionId, rows) => {
    edits.current += 1;
    setHighlights((all) => [...all.filter((h) => h.micro_session_id !== microSessionId), ...rows]);
  }, []);

  return { highlights, setHighlights, replaceForPart };
}
