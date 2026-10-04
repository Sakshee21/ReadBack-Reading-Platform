import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { logEvent } from "../api";

export default function NudgeBanner({ nudge, onDismiss }) {
  const navigate = useNavigate();
  const visible = Boolean(nudge && nudge.kind);

  useEffect(() => {
    if (!visible) return;
    logEvent("nudge_shown", {
      bookId: nudge.book_id,
      nudge_kind: nudge.kind,
      days_away: nudge.days_away,
    });
  }, [visible, nudge?.kind, nudge?.book_id, nudge?.days_away]);

  if (!visible) return null;

  function handleContinue() {
    logEvent("nudge_clicked", {
      bookId: nudge.book_id,
      nudge_kind: nudge.kind,
      days_away: nudge.days_away,
    });
    if (nudge.book_id) navigate(`/read/${nudge.book_id}`);
  }

  function handleDismiss() {
    logEvent("nudge_dismissed", {
      bookId: nudge.book_id,
      nudge_kind: nudge.kind,
      days_away: nudge.days_away,
    });
    onDismiss();
  }

  return (
    <div className={`nudge-banner ${nudge.kind}`}>
      <span className="nudge-message">{nudge.message}</span>
      <div className="nudge-actions">
        {nudge.book_id && (
          <button className="btn-primary" style={{ width: "auto" }} onClick={handleContinue}>
            Continue reading
          </button>
        )}
        <button className="btn-secondary" onClick={handleDismiss}>
          Not now
        </button>
      </div>
    </div>
  );
}
