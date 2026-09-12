import datetime as dt

from app.services.streak import apply_completed_session, streak_after_gap

TODAY = dt.date(2026, 3, 10)
YESTERDAY = TODAY - dt.timedelta(days=1)
TWO_DAYS_AGO = TODAY - dt.timedelta(days=2)


def test_first_ever_session_starts_streak_at_one():
    current, longest, last = apply_completed_session(0, 0, None, TODAY)
    assert (current, longest, last) == (1, 1, TODAY)


def test_consecutive_day_increments_streak():
    current, longest, last = apply_completed_session(3, 5, YESTERDAY, TODAY)
    assert (current, longest, last) == (4, 5, TODAY)


def test_consecutive_day_increments_longest_when_it_overtakes():
    current, longest, last = apply_completed_session(5, 5, YESTERDAY, TODAY)
    assert (current, longest, last) == (6, 6, TODAY)


def test_missed_day_resets_streak_to_one():
    current, longest, last = apply_completed_session(10, 10, TWO_DAYS_AGO, TODAY)
    assert (current, longest, last) == (1, 10, TODAY)


def test_missed_many_days_resets_streak_to_one():
    long_ago = TODAY - dt.timedelta(days=30)
    current, longest, last = apply_completed_session(10, 10, long_ago, TODAY)
    assert (current, longest, last) == (1, 10, TODAY)


def test_second_completed_session_same_day_does_not_double_increment():
    current, longest, last = apply_completed_session(4, 4, TODAY, TODAY)
    assert (current, longest, last) == (4, 4, TODAY)


def test_first_session_ever_same_day_repeat_stays_at_one():
    current, longest, last = apply_completed_session(0, 0, TODAY, TODAY)
    assert (current, longest, last) == (1, 1, TODAY)


def test_streak_after_gap_no_history_is_zero():
    assert streak_after_gap(0, None, TODAY) == 0


def test_streak_after_gap_same_day_is_unchanged():
    assert streak_after_gap(5, TODAY, TODAY) == 5


def test_streak_after_gap_yesterday_is_unchanged_until_next_session():
    assert streak_after_gap(5, YESTERDAY, TODAY) == 5


def test_streak_after_gap_missed_day_resets_to_zero():
    assert streak_after_gap(5, TWO_DAYS_AGO, TODAY) == 0
