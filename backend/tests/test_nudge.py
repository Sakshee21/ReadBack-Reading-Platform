import datetime as dt

from app.services.nudge import AWAY, STREAK_AT_RISK, choose_nudge

TODAY = dt.date(2026, 3, 10)
AWAY_DAYS = 3


def _days_ago(n):
    return TODAY - dt.timedelta(days=n)


def test_no_nudge_for_a_user_who_never_read():
    assert choose_nudge(None, 0, TODAY, AWAY_DAYS) is None


def test_no_nudge_when_already_read_today():
    assert choose_nudge(TODAY, 5, TODAY, AWAY_DAYS) is None


def test_streak_at_risk_the_day_after_reading():
    assert choose_nudge(_days_ago(1), 5, TODAY, AWAY_DAYS) == STREAK_AT_RISK


def test_no_streak_nudge_without_a_live_streak():
    # streak already broken, and not away long enough yet
    assert choose_nudge(_days_ago(2), 0, TODAY, AWAY_DAYS) is None


def test_away_nudge_at_the_threshold():
    assert choose_nudge(_days_ago(3), 0, TODAY, AWAY_DAYS) == AWAY


def test_away_nudge_beyond_the_threshold():
    assert choose_nudge(_days_ago(30), 0, TODAY, AWAY_DAYS) == AWAY


def test_away_takes_priority_over_streak():
    assert choose_nudge(_days_ago(5), 9, TODAY, AWAY_DAYS) == AWAY


def test_away_days_is_configurable():
    assert choose_nudge(_days_ago(2), 0, TODAY, away_days=2) == AWAY
    assert choose_nudge(_days_ago(2), 0, TODAY, away_days=10) is None


def test_future_last_read_date_is_not_a_nudge():
    assert choose_nudge(TODAY + dt.timedelta(days=1), 3, TODAY, AWAY_DAYS) is None
