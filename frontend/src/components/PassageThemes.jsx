import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";

/**
 * The themes of the passage being read, shown after its text when the reader
 * has switched theme tags on. Quiet by design: no tags and nothing pending
 * renders nothing, and a failed lookup never disturbs reading.
 */
export default function PassageThemes({ bookId, microSessionId }) {
  const [state, setState] = useState({ themes: [], preparing: false });

  useEffect(() => {
    let current = true;
    setState({ themes: [], preparing: false });
    api
      .getPassageThemes(bookId, microSessionId)
      .then((result) => {
        if (current) setState({ themes: result.themes || [], preparing: Boolean(result.preparing) });
      })
      .catch(() => {});
    return () => {
      current = false;
    };
  }, [bookId, microSessionId]);

  if (state.themes.length > 0) {
    return (
      <ul className="theme-chips passage-themes" aria-label="Themes in this passage">
        {state.themes.map((t) => (
          <li key={t.theme}>
            <Link to={`/books/${bookId}/themes`} className="theme-chip">
              {t.label}
            </Link>
          </li>
        ))}
      </ul>
    );
  }
  if (state.preparing) return <p className="passage-themes-note">Themes are still being prepared.</p>;
  return null;
}
