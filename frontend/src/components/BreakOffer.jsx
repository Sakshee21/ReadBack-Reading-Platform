import { useEffect, useRef } from "react";
import { useDialogKeys } from "../breaks/useDialogKeys";

export default function BreakOffer({ onAccept, onDecline }) {
  const dialogRef = useRef(null);
  const acceptRef = useRef(null);

  // Escape is a quick "no thanks"; Tab stays inside the dialog.
  useDialogKeys(dialogRef, onDecline);

  useEffect(() => {
    acceptRef.current?.focus();
  }, []);

  return (
    <div className="brk-overlay">
      <div
        ref={dialogRef}
        className="brk-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="brk-offer-title"
      >
        <h2 id="brk-offer-title" className="brk-title">
          Feeling tired?
        </h2>
        <p className="brk-text">Take a 2-minute break with a small puzzle.</p>
        <div className="brk-actions">
          <button ref={acceptRef} type="button" className="btn-primary" style={{ width: "auto" }} onClick={onAccept}>
            Yes, a short break
          </button>
          <button type="button" className="btn-secondary" onClick={onDecline}>
            No thanks, keep reading
          </button>
        </div>
      </div>
    </div>
  );
}
