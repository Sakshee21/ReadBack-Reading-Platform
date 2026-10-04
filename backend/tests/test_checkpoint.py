from app.services.checkpoint import is_quiz_due, score_attempt

SEQ = {
    "id": "q1",
    "question_type": "sequencing",
    "prompt": "order them",
    "items": ["b", "a", "c"],
    "answer": ["a", "b", "c"],
}
REL = {
    "id": "q2",
    "question_type": "relationship",
    "prompt": "match them",
    "left_items": ["x", "y"],
    "options": ["one", "two"],
    "answer": {"x": "one", "y": "two"},
}
INF = {
    "id": "q3",
    "question_type": "inference",
    "prompt": "why?",
    "options": ["right", "wrong"],
    "answer": "right",
}


# --- cadence ---


def test_default_cadence_serves_every_authored_checkpoint():
    assert all(is_quiz_due(i, 1) for i in range(12))


def test_cadence_of_ten_only_fires_on_multiples():
    assert is_quiz_due(0, 10) is True
    assert is_quiz_due(10, 10) is True
    assert is_quiz_due(9, 10) is False
    assert is_quiz_due(15, 10) is False


def test_cadence_guards_against_zero_or_negative():
    assert is_quiz_due(7, 0) is True
    assert is_quiz_due(7, -3) is True


# --- scoring by question type ---


def test_sequencing_exact_order_is_correct():
    score, correct, total = score_attempt([SEQ], {"q1": ["a", "b", "c"]})
    assert (score, correct, total) == (100.0, 1, 1)


def test_sequencing_wrong_order_is_incorrect():
    assert score_attempt([SEQ], {"q1": ["b", "a", "c"]})[1] == 0


def test_sequencing_partial_answer_is_incorrect():
    assert score_attempt([SEQ], {"q1": ["a", "b"]})[1] == 0


def test_sequencing_is_case_insensitive():
    assert score_attempt([SEQ], {"q1": ["A", "B", "C"]})[1] == 1


def test_relationship_full_match_is_correct():
    assert score_attempt([REL], {"q2": {"x": "one", "y": "two"}})[1] == 1


def test_relationship_one_wrong_pair_fails():
    assert score_attempt([REL], {"q2": {"x": "two", "y": "one"}})[1] == 0


def test_relationship_missing_pair_fails():
    assert score_attempt([REL], {"q2": {"x": "one"}})[1] == 0


def test_inference_scoring():
    assert score_attempt([INF], {"q3": "right"})[1] == 1
    assert score_attempt([INF], {"q3": "wrong"})[1] == 0


def test_wrong_shape_answer_is_never_correct():
    assert score_attempt([SEQ], {"q1": "a"})[1] == 0
    assert score_attempt([REL], {"q2": ["one", "two"]})[1] == 0
    assert score_attempt([INF], {"q3": ["right"]})[1] == 0


def test_mixed_quiz_scores_proportionally():
    score, correct, total = score_attempt(
        [SEQ, REL, INF], {"q1": ["a", "b", "c"], "q2": {"x": "one", "y": "two"}, "q3": "wrong"}
    )
    assert (correct, total) == (2, 3)
    assert score == 66.67


def test_unanswered_questions_score_zero():
    assert score_attempt([SEQ, REL, INF], {}) == (0.0, 0, 3)


def test_legacy_type_field_still_scores():
    legacy = {"id": "q", "type": "inference", "options": ["a"], "answer": "a"}
    assert score_attempt([legacy], {"q": "a"})[1] == 1


def test_empty_quiz():
    assert score_attempt([], {}) == (0.0, 0, 0)
