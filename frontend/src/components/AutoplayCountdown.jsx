import { useEffect, useRef, useState } from "react";

export default function AutoplayCountdown({ seconds = 3, onComplete, onCancel }) {
  const [remaining, setRemaining] = useState(seconds);
  const [paused, setPaused] = useState(false);
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  useEffect(() => {
    if (paused) return;
    if (remaining <= 0) {
      onCompleteRef.current();
      return;
    }
    const timer = setTimeout(() => setRemaining((r) => r - 1), 1000);
    return () => clearTimeout(timer);
  }, [remaining, paused]);

  return (
    <div className="countdown-overlay">
      <div className="countdown-card">
        <div className="countdown-number">{remaining}</div>
        <p>Next micro-session starting{paused ? " (paused)" : "..."}</p>
        <div className="countdown-actions">
          <button className="btn-secondary" onClick={() => setPaused((p) => !p)}>
            {paused ? "Resume" : "Pause"}
          </button>
          <button className="btn-secondary" onClick={onCancel}>
            Cancel
          </button>
          <button className="btn-primary" style={{ width: "auto" }} onClick={onComplete}>
            Continue now
          </button>
        </div>
      </div>
    </div>
  );
}
