"""Daily reading streak logic.

A streak increments once per calendar day on the first completed
ReadingSession that day, and resets to 1 if a calendar day is skipped.
Kept as pure functions (no DB/session access) so the edge cases around
day boundaries are easy to unit test.
"""

import datetime as dt


def apply_completed_session(
    current_streak: int,
    longest_streak: int,
    last_read_date: dt.date | None,
    today: dt.date,
) -> tuple[int, int, dt.date]:
    """Returns (new_current_streak, new_longest_streak, new_last_read_date)."""
    if last_read_date == today:
        new_current = max(current_streak, 1)
    elif last_read_date == today - dt.timedelta(days=1):
        new_current = current_streak + 1
    else:
        new_current = 1

    new_longest = max(longest_streak, new_current)
    return new_current, new_longest, today


def streak_after_gap(current_streak: int, last_read_date: dt.date | None, today: dt.date) -> int:
    """What the streak *would show as* right now, without a new completed
    session today (e.g. for display) — a missed day resets it to 0."""
    if last_read_date is None:
        return 0
    if last_read_date in (today, today - dt.timedelta(days=1)):
        return current_streak
    return 0
