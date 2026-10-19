import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { api, logEvent } from "../api";
import RecapBanner from "../components/RecapBanner";
import VisualizationPrompt from "../components/VisualizationPrompt";
import AutoplayCountdown from "../components/AutoplayCountdown";
import RSVPMode from "../components/RSVPMode";
import CheckpointQuiz from "../components/CheckpointQuiz";
import StreakDisplay from "../components/StreakDisplay";
import PaceDisplay from "../components/PaceDisplay";
import SessionDrawer from "../components/SessionDrawer";
import ProgressRing from "../components/ProgressRing";
import SettingsPanel from "../components/SettingsPanel";
import CelebrationOverlay, { celebrationFor } from "../components/CelebrationOverlay";
import Icon from "../components/Icon";
import BreakOffer from "../components/BreakOffer";
import BreakShell from "../components/BreakShell";
import { useBreakFlow } from "../breaks/useBreakFlow";
import { useSettings } from "../SettingsContext";
import HighlightableText from "../components/HighlightableText";
import PassageThemes from "../components/PassageThemes";
import { useBookHighlights } from "../highlights/useBookHighlights";
import { highlightingEnabled, loadInitialPosition, parseDeepLink, partsOf } from "../highlights/readerGlue";

export default function Reader() {
  const { bookId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [position, setPosition] = useState(null);
  const [focusHighlightId, setFocusHighlightId] = useState(null);
  const [streak, setStreak] = useState(null);
  const [pace, setPace] = useState(null);
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
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [celebration, setCelebration] = useState(null);
  const [streakBump, setStreakBump] = useState(false);
  const [scrollProgress, setScrollProgress] = useState(0);
  const { plainTheme, offerBreaks, showThemeTags } = useSettings();
  // advanceToNextPosition is declared further down; the break flow reaches it
  // through this ref so the hook can be called before it exists.
  const advanceRef = useRef(null);
  const breaks = useBreakFlow({
    enabled: offerBreaks,
    // The offer waits while any other overlay is up so overlays never stack.
    celebrationActive:
      celebration !== null || drawerOpen || settingsOpen || unstuckPrompt || burstParagraph !== null,
    resume: () => advanceRef.current?.(),
  });
  const clearFocusHighlight = useCallback(() => setFocusHighlightId(null), []);
  // A consented upload is tagged with themes in the background while it is read.
  // Fire and forget: reading never waits for it and a failure changes nothing.
  const themeBook = position?.book;
  const prefetchKey = position?.micro_session?.id ?? null;
  const tagThemesAhead = Boolean(themeBook?.theme_tagging_enabled);
  useEffect(() => {
    if (!tagThemesAhead || prefetchKey == null) return;
    api.prefetchThemes(themeBook.id, prefetchKey).catch(() => {});
  }, [tagThemesAhead, prefetchKey, themeBook?.id]);
  const { highlights, replaceForPart } = useBookHighlights(bookId, position?.micro_session?.id ?? null);
  const startedForMicroSession = useRef(null);
  const contentAreaRef = useRef(null);
  const topbarRef = useRef(null);
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
    if (!log) return 0;
    const now = Date.now();
    const hidden = log.hiddenAccum + (log.hiddenSince ? now - log.hiddenSince : 0);
    const activeMs = Math.max(0, now - log.startedAt - hidden);
    logEvent("session_end", {
      bookId: log.bookId,
      chapterId: log.chapterId,
      microSessionId: log.microSessionId,
      reason,
      // word_count travels with active_ms so reading pace is derivable from
      // the event log alone (see services/pace.py).
      word_count: log.wordCount,
      active_ms: activeMs,
    });
    sessionLog.current = null;
    return activeMs;
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
    // Arriving from the notes page: open at that passage and focus the highlight.
    const link = parseDeepLink(location.search);
    Promise.all([loadInitialPosition(api, bookId, link.ms), api.getStreak(), api.getPace(bookId)])
      .then(([pos, streakData, paceData]) => {
        if (link.ms) {
          setFocusHighlightId(link.h);
          navigate(`/read/${bookId}`, { replace: true });
        }
        setPosition(pos);
        setStreak(streakData);
        setPace(paceData);
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
        breaks.onSessionStart();
        endSessionLog("advance");
        sessionLog.current = {
          ...ctx,
          wordCount: position.micro_session.word_count,
          startedAt: Date.now(),
          hiddenAccum: 0,
          hiddenSince: null,
        };
        logEvent("session_start", { ...ctx, word_count: position.micro_session.word_count });
      })
      .catch((err) => setError(err.message || "Could not start session"));
  }, [position, bookId, endSessionLog, breaks.onSessionStart]);

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
    rsvpActive ||
    burstParagraph !== null ||
    countdownActive ||
    awaitingManualContinue ||
    unstuckPrompt ||
    breaks.phase !== "idle";
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
    setScrollProgress(0);
  }, [position?.micro_session?.id]);

  // Decorative mood tint for this book, applied to the document so the whole
  // page (not just a panel) picks it up. "Plain theme" opts out entirely.
  const bookTheme = position?.book?.theme;
  useEffect(() => {
    if (!bookTheme || plainTheme) {
      delete document.documentElement.dataset.theme;
      return;
    }
    document.documentElement.dataset.theme = bookTheme;
    return () => {
      delete document.documentElement.dataset.theme;
    };
  }, [bookTheme, plainTheme]);

  // How far through the current session the reader has scrolled - drives the
  // progress ring. Passive listener so it never janks scrolling.
  useEffect(() => {
    function onScroll() {
      const scrollable = document.documentElement.scrollHeight - window.innerHeight;
      setScrollProgress(scrollable > 0 ? Math.min(1, window.scrollY / scrollable) : 1);
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener("scroll", onScroll);
  }, [position?.micro_session?.id]);

  // The RSVP control bar sticks *below* the topbar, whose height changes when
  // the controls wrap on narrow screens - so publish the measured height as a
  // CSS variable instead of hard-coding an offset.
  useEffect(() => {
    const el = topbarRef.current;
    if (!el) return;
    const publish = () =>
      document.documentElement.style.setProperty(
        "--reader-topbar-h",
        `${Math.round(el.getBoundingClientRect().height)}px`
      );
    publish();
    const observer = new ResizeObserver(publish);
    observer.observe(el);
    return () => {
      observer.disconnect();
      document.documentElement.style.removeProperty("--reader-topbar-h");
    };
  }, [position?.book?.id, bookFinished]);

  // Brief pop when the streak goes up.
  useEffect(() => {
    if (!streakBump) return;
    const timer = setTimeout(() => setStreakBump(false), 700);
    return () => clearTimeout(timer);
  }, [streakBump]);

  const advanceToNextPosition = useCallback(() => {
    api
      .getReaderPosition(bookId)
      .then((pos) => {
        setPosition(pos);
        setSessionId(null);
      })
      .catch((err) => setError(err.message || "Could not load next session"));
  }, [bookId]);
  advanceRef.current = advanceToNextPosition;

  const jumpTo = useCallback(
    (microSessionId) => {
      endSessionLog("jump");
      breaks.cancelDue();
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
    [bookId, endSessionLog, breaks.cancelDue]
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
      const activeMs = endSessionLog("complete");

      if (result.session_size_changed) {
        logEvent("session_size", { bookId: ctx.bookId, level: result.session_size_level });
      }

      // Reward animation. The rule is deterministic (see CelebrationOverlay):
      // a milestone burst only when this completion lands the streak exactly
      // on 3, 7 or 14 days, otherwise the standard one.
      const streakBefore = streak?.current_streak ?? 0;
      const streakAfter = result.streak.current_streak;
      setCelebration(celebrationFor({ streakBefore, streakAfter }));
      if (streakAfter > streakBefore) setStreakBump(true);

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

      // Refresh pace once per completed session - the session_end event this
      // completion just logged is the newest sample.
      api
        .getPace(bookId)
        .then((fresh) => {
          setPace(fresh);
          if (fresh.wpm_average) {
            logEvent("pace_updated", {
              bookId: ctx.bookId,
              wpm_recent: fresh.wpm_recent,
              wpm_average: fresh.wpm_average,
              trend: fresh.trend,
            });
          }
        })
        .catch(() => {});
      if (result.finished_book) {
        setBookFinished(true);
      } else {
        // When a break is pending the offer replaces the autoplay countdown.
        const breakPending = breaks.onSessionComplete({
          activeMs,
          quizDue: Boolean(result.checkpoint_due),
          finished: false,
          ctx,
        });
        if (!breakPending) setCountdownActive(true);
      }
    } catch (err) {
      setError(err.message || "Could not save your progress");
    }
  }

  function handleCheckpointDone() {
    breaks.onQuizDone();
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
  const canHighlight = highlightingEnabled({
    rsvpActive,
    celebrationActive: celebration !== null,
    drawerOpen,
    settingsOpen,
    quizDue: Boolean(position.checkpoint_due),
    unstuckPrompt,
    burstActive: burstParagraph !== null,
    countdownActive,
    breakPhase: breaks.phase,
  });

  return (
    <div className="reader-page">
      <div className="reader-topbar" ref={topbarRef}>
        <div>
          <div className="book-title">{position.book.title}</div>
          <div className="chapter-label">{position.chapter_title || `Chapter ${position.chapter_index + 1}`}</div>
        </div>
        <div className="controls">
          <ProgressRing value={scrollProgress} />
          <StreakDisplay streak={streak} bump={streakBump} />
          <PaceDisplay pace={pace} />
          <button
            className={`icon-btn ${rsvpActive ? "active" : ""}`}
            onClick={() => setRsvpActive((a) => !a)}
          >
            <Icon name="rsvp" />
            RSVP mode
          </button>
          <button className="icon-btn" onClick={() => setDrawerOpen(true)}>
            <Icon name="sessions" />
            Sessions
          </button>
          <button className="icon-btn" onClick={() => setSettingsOpen(true)}>
            <Icon name="settings" />
            Settings
          </button>
          <Link to={`/books/${position.book.id}/themes`} className="icon-btn">
            <Icon name="themes" />
            Themes
          </Link>
          <Link to={`/books/${position.book.id}/notes`} className="icon-btn">
            <Icon name="notes" />
            Notes
          </Link>
          <Link to="/library" className="icon-btn">
            <Icon name="library" />
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
            <div className="fade-in-text" key={position.micro_session.id}>
              {partsOf(position.micro_session).map((part) => (
                <HighlightableText
                  key={part.id}
                  text={part.text}
                  bookId={position.book.id}
                  microSessionId={part.id}
                  enabled={canHighlight}
                  highlights={highlights.filter((h) => h.micro_session_id === part.id)}
                  onChanged={(rows) => replaceForPart(part.id, rows)}
                  focusHighlightId={focusHighlightId}
                  onFocused={clearFocusHighlight}
                />
              ))}
            </div>
          )}
          {showThemeTags && !rsvpActive && (
            <PassageThemes bookId={position.book.id} microSessionId={position.micro_session.id} />
          )}
          {position.micro_session.has_visualization_prompt && <VisualizationPrompt {...logCtx} />}
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

      {breaks.phase === "offered" && <BreakOffer onAccept={breaks.accept} onDecline={breaks.decline} />}

      {(breaks.phase === "playing" || breaks.phase === "ended") && breaks.game && (
        <BreakShell
          game={breaks.game}
          puzzle={breaks.puzzle}
          seed={breaks.seed}
          rounds={breaks.rounds}
          startedAt={breaks.startedAt}
          onFinish={breaks.finish}
          onDone={breaks.done}
          onError={breaks.onGameError}
        />
      )}

      <CelebrationOverlay
        celebration={celebration}
        {...logCtx}
        onDone={() => setCelebration(null)}
      />

      <SessionDrawer
        open={drawerOpen}
        items={sessionList}
        onClose={() => setDrawerOpen(false)}
        onSelect={handleDrawerSelect}
      />

      <SettingsPanel
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        bookId={position.book.id}
      />
    </div>
  );
}
