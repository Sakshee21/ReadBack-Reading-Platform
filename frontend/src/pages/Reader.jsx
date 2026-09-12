import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import RecapBanner from "../components/RecapBanner";
import VisualizationPrompt from "../components/VisualizationPrompt";
import AutoplayCountdown from "../components/AutoplayCountdown";
import RSVPMode from "../components/RSVPMode";
import CheckpointQuiz from "../components/CheckpointQuiz";
import StreakDisplay from "../components/StreakDisplay";

export default function Reader() {
  const { bookId } = useParams();
  const [position, setPosition] = useState(null);
  const [streak, setStreak] = useState(null);
  const [sessionId, setSessionId] = useState(null);
  const [rsvpActive, setRsvpActive] = useState(false);
  const [countdownActive, setCountdownActive] = useState(false);
  const [awaitingManualContinue, setAwaitingManualContinue] = useState(false);
  const [bookFinished, setBookFinished] = useState(false);
  const [error, setError] = useState("");
  const startedForMicroSession = useRef(null);

  useEffect(() => {
    setPosition(null);
    setBookFinished(false);
    startedForMicroSession.current = null;
    Promise.all([api.getReaderPosition(bookId), api.getStreak()])
      .then(([pos, streakData]) => {
        setPosition(pos);
        setStreak(streakData);
      })
      .catch((err) => setError(err.message || "Could not load this book"));
  }, [bookId]);

  useEffect(() => {
    if (!position || position.checkpoint_due) return;
    const msId = position.micro_session.id;
    if (startedForMicroSession.current === msId) return;
    startedForMicroSession.current = msId;
    api
      .startSession(Number(bookId), msId)
      .then((session) => setSessionId(session.id))
      .catch((err) => setError(err.message || "Could not start session"));
  }, [position, bookId]);

  const advanceToNextPosition = useCallback(() => {
    api
      .getReaderPosition(bookId)
      .then((pos) => {
        setPosition(pos);
        setSessionId(null);
      })
      .catch((err) => setError(err.message || "Could not load next session"));
  }, [bookId]);

  async function handleFinishMicroSession() {
    if (!sessionId) return;
    try {
      const result = await api.completeSession(sessionId);
      setStreak(result.streak);
      setSessionId(null);
      if (result.finished_book) {
        setBookFinished(true);
      } else {
        setCountdownActive(true);
      }
    } catch (err) {
      setError(err.message || "Could not save your progress");
    }
  }

  function handleCheckpointDone() {
    setPosition((p) => ({ ...p, checkpoint_due: null }));
  }

  if (error) return <div className="page-loading">{error}</div>;
  if (!position) return <div className="page-loading">Loading book...</div>;

  if (bookFinished) {
    return (
      <div className="reader-page">
        <div className="reader-body">
          <div className="reader-content" style={{ textAlign: "center" }}>
            <h1>You finished "{position.book.title}"!</h1>
            <p>Great work reaching the end. Pick something else to read next.</p>
            <Link to="/library" className="btn-primary" style={{ display: "inline-block", width: "auto" }}>
              Back to library
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (position.checkpoint_due) {
    return <CheckpointQuiz checkpoint={position.checkpoint_due} onDone={handleCheckpointDone} />;
  }

  return (
    <div className="reader-page">
      <div className="reader-topbar">
        <div>
          <div className="book-title">{position.book.title}</div>
          <div className="chapter-label">{position.chapter_title || `Chapter ${position.chapter_index + 1}`}</div>
        </div>
        <div className="controls">
          <StreakDisplay streak={streak} />
          <button
            className={`icon-btn ${rsvpActive ? "active" : ""}`}
            onClick={() => setRsvpActive((a) => !a)}
          >
            RSVP mode
          </button>
          <Link to="/library" className="icon-btn">
            Library
          </Link>
        </div>
      </div>
      <div className="reader-progress-track">
        <div className="fill" style={{ width: `${Math.min(position.progress_pct, 100)}%` }} />
      </div>

      <div className="reader-body">
        <div className="reader-content">
          <RecapBanner recap={position.recap} />
          {rsvpActive ? (
            <RSVPMode
              key={position.micro_session.id}
              text={position.micro_session.text}
              onExit={() => setRsvpActive(false)}
            />
          ) : (
            position.micro_session.text.split(/\n{2,}/).map((paragraph, i) => <p key={i}>{paragraph}</p>)
          )}
          {position.micro_session.has_visualization_prompt && <VisualizationPrompt />}
        </div>
      </div>

      <div className="reader-footer">
        {awaitingManualContinue ? (
          <button
            className="btn-primary"
            onClick={() => {
              setAwaitingManualContinue(false);
              advanceToNextPosition();
            }}
          >
            Continue reading
          </button>
        ) : (
          <button className="btn-primary" onClick={handleFinishMicroSession} disabled={!sessionId}>
            {position.micro_session.is_cliffhanger_break ? "Finish this cliffhanger" : "Continue"}
          </button>
        )}
      </div>

      {countdownActive && (
        <AutoplayCountdown
          seconds={3}
          onComplete={() => {
            setCountdownActive(false);
            advanceToNextPosition();
          }}
          onCancel={() => {
            setCountdownActive(false);
            setAwaitingManualContinue(true);
          }}
        />
      )}
    </div>
  );
}
