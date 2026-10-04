"""Adaptive reading pace, derived from the pilot event log.

Pace is words per minute of *active* time, taken from `session_end` events
(which carry both word_count and active_ms). Samples that are obviously not
reading - a session abandoned after two seconds, a tab left open overnight -
are discarded so one outlier can't wreck the estimate.
"""

# Plausibility bounds for a single sample.
MIN_ACTIVE_MS = 5_000           # 5s: anything shorter wasn't read
MAX_ACTIVE_MS = 2 * 60 * 60_000  # 2h: tab was almost certainly left open
MIN_WORDS = 50
MAX_PLAUSIBLE_WPM = 2000

ROLLING_WINDOW = 20
RECENT_WINDOW = 3
TREND_DEADBAND = 0.05

DEFAULT_WPM = 200  # matches segmentation.WORDS_PER_MINUTE


def sample_wpm(words: int | None, active_ms: int | None) -> float | None:
    """Words per minute for one session, or None if it isn't a usable sample."""
    if not words or not active_ms:
        return None
    if words < MIN_WORDS or not (MIN_ACTIVE_MS <= active_ms <= MAX_ACTIVE_MS):
        return None
    wpm = words / (active_ms / 60_000)
    if wpm <= 0 or wpm > MAX_PLAUSIBLE_WPM:
        return None
    return wpm


def trend_label(recent: float | None, average: float | None, deadband: float = TREND_DEADBAND) -> str:
    if not recent or not average:
        return "steady"
    if recent > average * (1 + deadband):
        return "faster"
    if recent < average * (1 - deadband):
        return "slower"
    return "steady"


def minutes_for(words: int, wpm: float | None) -> float | None:
    if not words or not wpm or wpm <= 0:
        return None
    return round(words / wpm, 1)


def summarize(samples: list[tuple[int | None, int | None]]) -> dict:
    """``samples`` is (words, active_ms) ordered newest first."""
    wpms = [w for w in (sample_wpm(words, ms) for words, ms in samples) if w is not None]
    if not wpms:
        return {
            "wpm_recent": None,
            "wpm_average": None,
            "sessions_counted": 0,
            "trend": "steady",
            "is_estimate": True,
        }

    rolling = wpms[:ROLLING_WINDOW]
    recent = wpms[:RECENT_WINDOW]
    wpm_recent = round(sum(recent) / len(recent), 1)
    wpm_average = round(sum(rolling) / len(rolling), 1)
    return {
        "wpm_recent": wpm_recent,
        "wpm_average": wpm_average,
        "sessions_counted": len(rolling),
        "trend": trend_label(wpm_recent, wpm_average),
        "is_estimate": False,
    }
