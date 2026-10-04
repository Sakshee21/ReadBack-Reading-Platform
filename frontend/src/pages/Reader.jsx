import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, logEvent } from "../api";
import RecapBanner from "../components/RecapBanner";
import VisualizationPrompt from "../components/VisualizationPrompt";
import AutoplayCountdown from "../components/AutoplayCountdown";
import RSVPMode from "../components/RSVPMode";
import CheckpointQuiz from "../components/CheckpointQuiz";
import StreakDisplay from "../components/StreakDisplay";
import SessionDrawer from "../components/SessionDrawer";

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
  const [sessionList, setSessionList] = useState([]);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [recapHidden, setRecapHidden] = useState(false);
  const [unstuckPrompt, setUnstuckPrompt] = useState(false);
  const [burstParagraph, setBurstParagraph] = useState(null);
  const startedForMicroSession = useRef(null);
  const contentAreaRef = useRef(null);
  // Micro-session id the unstuck prompt has already been resolved for, so we
  // don't re-prompt in the same session after an accept or decline.
  const unstuckResolvedRef = useRef(null);
  const INACTIVITY_MS = 25000;

  // Active-reading-time tracking for session_start / session_end events. We
  // subtract time the tab was hidden so "active duration" reflects attention,
  // not wall-clock elapsed time.
  const sessionLog = useRef(null);
  const prevStreak = useRef(null);

  const endSessionLog = useCallback((reason) => {
    const log = sessionLog.current;
    if (!log) return;
    const now = Date.now();
    const hidden = log.hiddenAccum + (log.hiddenSince ? now - log.hiddenSince : 0);
    logEvent("session_end", {
      bookId: log.bookId,
      chapterId: log.chapterId,
      microSessionId: log.microSessionId,
      reason,
      active_ms: Math.max(0, now - log.startedAt - hidden),
    });
    sessionLog.current = null;
  }, []);

  // Accumulate hidden time onto the active session log across tab switches.
  useEffect(() => {
    function onVisibility() {
      const log = sessionLog.current;
      if (!log) return;
      if (document.hidden) {
        log.hiddenSince = Date.now();
      } else if (log.hiddenSince) {
        log.hiddenAccum += Date.now() - log.hiddenSince;
        log.hiddenSince = null;
      }
    }
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      endSessionLog("navigate");
    };
  }, [endSessionLog]);

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
    const ctx = {
      bookId: position.book.id,
      chapterId: position.chapter_id,
      microSessionId: msId,
    };
    api
      .startSession(Number(bookId), msId)
      .then((session) => {
        setSessionId(session.id);
        endSessionLog("advance");
        sessionLog.current = { ...ctx, startedAt: Date.now(), hiddenAccum: 0, hiddenSince: null };
        logEvent("session_start", { ...ctx, word_count: position.micro_session.word_count });
      })
      .catch((err) => setError(err.message || "Could not start session"));
  }, [position, bookId, endSessionLog]);

  // Reset the per-micro-session recap state and log that a recap was shown.
  useEffect(() => {
    if (!position) return;
    setRecapHidden(false);
    setUnstuckPrompt(false);
    setBurstParagraph(null);
    unstuckResolvedRef.current = null;
    if (position.recap) {
      logEvent("recap_shown", {
        bookId: position.book.id,
        chapterId: position.chapter_id,
        microSessionId: position.micro_session.id,
      });
    }
  }, [position?.micro_session?.id]);

  // Mid-session inactivity watcher: if the reader goes ~25s with no scroll or
  // input while actively reading, offer a focus burst. Any interaction resets
  // the timer. Disarmed whenever another overlay/flow is active or the prompt
  // has already been resolved for this micro-session.
  const msId = position?.micro_session?.id;
  const readingActive = Boolean(position && !position.checkpoint_due && sessionId && !bookFinished);
  const unstuckBlocked =
    rsvpActive || burstParagraph !== null || countdownActive || awaitingManualContinue || unstuckPrompt;
  useEffect(() => {
    if (!readingActive || unstuckBlocked || unstuckResolvedRef.current === msId) return;
    let timer;
    const reset = () => {
      clearTimeout(timer);
      timer = setTimeout(() => setUnstuckPrompt(true), INACTIVITY_MS);
    };
    const activity = ["scroll", "keydown", "pointerdown", "mousemove", "wheel", "touchstart"];
    activity.forEach((e) => window.addEventListener(e, reset, { passive: true }));
    reset();
    return () => {
      clearTimeout(timer);
      activity.forEach((e) => window.removeEventListener(e, reset));
    };
  }, [readingActive, unstuckBlocked, msId]);

  function nextParagraphText() {
    const nodes = contentAreaRef.current?.querySelectorAll("p");
    if (nodes && nodes.length) {
      // first paragraph still at/below the top of the viewport (what the
      // reader is about to read), falling back to the first paragraph.
      const upcoming = Array.from(nodes).find((p) => p.getBoundingClientRect().bottom > 150);
      return (upcoming || nodes[0]).textContent.trim();
    }
    return position.micro_session.text.split(/\n{2,}/)[0] || "";
  }

  function acceptUnstuck() {
    const paragraph = nextParagraphText();
    logEvent("unstuck_accept", {
      bookId: position.book.id,
      chapterId: position.chapter_id,
      microSessionId: position.micro_session.id,
      paragraph_words: paragraph.split(/\s+/).filter(Boolean).length,
    });
    unstuckResolvedRef.current = position.micro_session.id;
    setUnstuckPrompt(false);
    setBurstParagraph(paragraph);
  }

  function declineUnstuck() {
    logEvent("unstuck_decline", {
      bookId: position.book.id,
      chapterId: position.chapter_id,
      microSessionId: position.micro_session.id,
    });
    unstuckResolvedRef.current = position.micro_session.id;
    setUnstuckPrompt(false);
  }

  // Keep the "jump to any session" drawer's completed/current markers fresh.
  useEffect(() => {
    if (!position) return;
    api.listMicroSessions(bookId).then(setSessionList).catch(() => {});
  }, [position, bookId]);

  // Always start a newly-shown micro-session scrolled to the top.
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [position?.micro_session?.id]);

  const advanceToNextPosition = useCallback(() => {
    api
      .getReaderPosition(bookId)
      .then((pos) => {
        setPosition(pos);
        setSessionId(null);
      })
      .catch((err) => setError(err.message || "Could not load next session"));
  }, [bookId]);

  const jumpTo = useCallback(
    (microSessionId) => {
      endSessionLog("jump");
      api
        .jumpToMicroSession(bookId, microSessionId)
        .then((pos) => {
          setPosition(pos);
          setSessionId(null);
          setAwaitingManualContinue(false);
          setCountdownActive(false);
          setRsvpActive(false);
        })
        .catch((err) => setError(err.message || "Could not jump to that session"));
    },
    [bookId, endSessionLog]
  );

  function handlePrevious() {
    const current = sessionList.find((item) => item.is_current);
    if (!current) return;
    const previous = sessionList.find((item) => item.session_number === current.session_number - 1);
    if (previous) jumpTo(previous.id);
  }

  function handleDrawerSelect(microSessionId) {
    setDrawerOpen(false);
    jumpTo(microSessionId);
  }

  const currentSessionNumber = sessionList.find((item) => item.is_current)?.session_number;
  const isFirstSession = currentSessionNumber === 1;

  async function handleFinishMicroSession() {
    if (!sessionId) return;
    const ctx = {
      bookId: position.book.id,
      chapterId: position.chapter_id,
      microSessionId: position.micro_session.id,
    };
    try {
      const result = await api.completeSession(sessionId);
      logEvent("session_complete", { ...ctx, word_count: position.micro_session.word_count });
      endSessionLog("complete");

      if (result.session_size_changed) {
        logEvent("session_size", { bookId: ctx.bookId, level: result.session_size_level });
      }

      const prev = prevStreak.current;
      if (!prev || prev.current_streak !== result.streak.current_streak ||
          prev.longest_streak !== result.streak.longest_streak) {
        logEvent("streak_updated", {
          bookId: ctx.bookId,
          current_streak: result.streak.current_streak,
          longest_streak: result.streak.longest_streak,
        });
      }
      prevStreak.current = result.streak;
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

  const logCtx = {
    bookId: position.book.id,
    chapterId: position.chapter_id,
    microSessionId: position.micro_session.id,
  };

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
          <button className="icon-btn" onClick={() => setDrawerOpen(true)}>
            Sessions
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
        <div className="reader-content" ref={contentAreaRef}>
          <RecapBanner
            recap={recapHidden ? null : position.recap}
            onDismiss={() => {
              setRecapHidden(true);
              logEvent("recap_dismissed", logCtx);
            }}
          />
          {rsvpActive ? (
            <RSVPMode
              key={position.micro_session.id}
              text={position.micro_session.text}
              mode="manual"
              {...logCtx}
              onExit={() => setRsvpActive(false)}
            />
          ) : (
            position.micro_session.text.split(/\n{2,}/).map((paragraph, i) => <p key={i}>{paragraph}</p>)
          )}
          {position.micro_session.has_visualization_prompt && (
            <VisualizationPrompt
              {...logCtx}
              image={position.micro_session.visualization_image}
              alt={position.micro_session.visualization_alt}
              attribution={position.micro_session.visualization_attribution}
            />
          )}
        </div>
      </div>

      <div className="reader-footer">
        <button className="btn-secondary" onClick={handlePrevious} disabled={isFirstSession || !currentSessionNumber}>
          Previous
        </button>
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

      {unstuckPrompt && (
        <div className="unstuck-toast">
          <span className="unstuck-text">Lost focus? Try a 20-second focus burst.</span>
          <div className="unstuck-actions">
            <button className="btn-primary" style={{ width: "auto" }} onClick={acceptUnstuck}>
              Focus burst
            </button>
            <button className="btn-secondary" onClick={declineUnstuck}>
              Dismiss
            </button>
          </div>
        </div>
      )}

      {burstParagraph !== null && (
        <div className="burst-overlay">
          <div className="burst-card">
            <div className="burst-label">20-second focus burst &middot; next paragraph</div>
            <RSVPMode
              key={`burst-${position.micro_session.id}`}
              text={burstParagraph}
              mode="burst"
              {...logCtx}
              onComplete={() => setBurstParagraph(null)}
              onExit={() => setBurstParagraph(null)}
            />
            <p className="burst-hint">Then you're back to normal reading, right where you left off.</p>
          </div>
        </div>
      )}

      {countdownActive && (
        <AutoplayCountdown
          seconds={3}
          {...logCtx}
          onComplete={() => {
            logEvent("autoplay_continue", logCtx);
            setCountdownActive(false);
            advanceToNextPosition();
          }}
          onCancel={() => {
            logEvent("autoplay_cancel", logCtx);
            setCountdownActive(false);
            setAwaitingManualContinue(true);
          }}
        />
      )}

      <SessionDrawer
        open={drawerOpen}
        items={sessionList}
        onClose={() => setDrawerOpen(false)}
        onSelect={handleDrawerSelect}
      />
    </div>
  );
}
