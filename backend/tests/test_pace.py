from app.services.pace import minutes_for, sample_wpm, summarize, trend_label

MIN = 60_000


def test_sample_wpm_basic():
    # 400 words in 2 minutes = 200 wpm
    assert sample_wpm(400, 2 * MIN) == 200


def test_sample_rejects_too_short_or_too_long():
    assert sample_wpm(400, 1_000) is None            # 1s - not reading
    assert sample_wpm(400, 3 * 60 * 60_000) is None  # 3h - tab left open


def test_sample_rejects_tiny_word_counts():
    assert sample_wpm(10, 2 * MIN) is None


def test_sample_rejects_implausible_speed():
    # 5000 words in 1 minute is skim-scrolling, not reading
    assert sample_wpm(5000, MIN) is None


def test_sample_handles_missing_data():
    assert sample_wpm(None, MIN) is None
    assert sample_wpm(400, None) is None
    assert sample_wpm(0, 0) is None


def test_summarize_with_no_usable_samples_is_an_estimate():
    out = summarize([(None, None), (10, 500)])
    assert out["is_estimate"] is True
    assert out["wpm_average"] is None
    assert out["sessions_counted"] == 0
    assert out["trend"] == "steady"


def test_summarize_averages_and_counts():
    out = summarize([(400, 2 * MIN), (400, 2 * MIN), (400, 2 * MIN)])
    assert out["wpm_average"] == 200
    assert out["wpm_recent"] == 200
    assert out["sessions_counted"] == 3
    assert out["is_estimate"] is False


def test_summarize_detects_speeding_up():
    # newest first: three fast sessions, then slow history
    samples = [(600, 2 * MIN)] * 3 + [(300, 2 * MIN)] * 10
    out = summarize(samples)
    assert out["wpm_recent"] > out["wpm_average"]
    assert out["trend"] == "faster"


def test_summarize_detects_slowing_down():
    samples = [(200, 2 * MIN)] * 3 + [(600, 2 * MIN)] * 10
    assert summarize(samples)["trend"] == "slower"


def test_summarize_ignores_outliers():
    clean = summarize([(400, 2 * MIN)] * 5)
    noisy = summarize([(400, 2 * MIN)] * 5 + [(999999, 1_000), (5, 10 * MIN)])
    assert clean["wpm_average"] == noisy["wpm_average"]


def test_trend_deadband_keeps_small_changes_steady():
    assert trend_label(202, 200) == "steady"
    assert trend_label(None, None) == "steady"
    assert trend_label(300, 200) == "faster"


def test_minutes_for():
    assert minutes_for(400, 200) == 2.0
    assert minutes_for(0, 200) is None
    assert minutes_for(400, None) is None
    assert minutes_for(400, 0) is None
