"""Gentle in-app reminder nudges.

In-app only - no email, no push. The rule, in priority order:

- ``away``           it has been at least ``away_days`` since the last read.
- ``streak_at_risk`` they read recently and still have a live streak, but not
                     today, so today is the day it breaks.

Pass the *live* streak (see services.streak.streak_after_gap): once a day has
been missed the streak is already gone, so there is nothing left to be at risk.
"""

import datetime as dt

AWAY = "away"
STREAK_AT_RISK = "streak_at_risk"


def choose_nudge(
    last_read_date: dt.date | None,
    live_streak: int,
    today: dt.date,
    away_days: int,
) -> str | None:
    if last_read_date is None:
        return None  # never read anything: nothing to resume

    days = (today - last_read_date).days
    if days <= 0:
        return None  # already read today

    if days >= away_days:
        return AWAY
    if live_streak > 0:
        return STREAK_AT_RISK
    return None
