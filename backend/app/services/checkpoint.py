"""Comprehension checkpoint cadence and scoring.

Cadence
-------
A checkpoint authored for chapter C is served when the reader reaches the start
of chapter C *and* ``C % quiz_every_n_chapters == 0``. The default of 1 means
every authored checkpoint fires (the original behaviour); raising it thins
quizzes out to every Nth chapter without touching the seed data.

Question types
--------------
Each question carries a ``question_type``:

- ``inference``    single choice from ``options``; answer is a string.
- ``sequencing``   put ``items`` in story order; answer is the ordered list.
- ``relationship`` match each of ``left_items`` to an entry in ``options``;
                   answer is a {left: right} mapping.

Scoring is all-or-nothing per question and always happens server-side.
"""

INFERENCE = "inference"
SEQUENCING = "sequencing"
RELATIONSHIP = "relationship"


def is_quiz_due(chapter_index: int, every_n_chapters: int) -> bool:
    """Whether a checkpoint authored for this chapter should be served now."""
    if every_n_chapters <= 1:
        return True
    return chapter_index % every_n_chapters == 0


def _norm(value) -> str:
    return str(value or "").strip().lower()


def _is_correct(question: dict, given) -> bool:
    qtype = question.get("question_type") or question.get("type") or INFERENCE
    expected = question.get("answer")

    if qtype == SEQUENCING:
        if not isinstance(given, list) or not isinstance(expected, list):
            return False
        if len(given) != len(expected):
            return False
        return [_norm(g) for g in given] == [_norm(e) for e in expected]

    if qtype == RELATIONSHIP:
        if not isinstance(given, dict) or not isinstance(expected, dict):
            return False
        if len(given) != len(expected):
            return False
        normalised_given = {_norm(k): _norm(v) for k, v in given.items()}
        normalised_expected = {_norm(k): _norm(v) for k, v in expected.items()}
        return normalised_given == normalised_expected

    # inference / legacy multiple choice
    if isinstance(given, (list, dict)):
        return False
    return bool(_norm(given)) and _norm(given) == _norm(expected)


def score_attempt(questions: list[dict], answers: dict) -> tuple[float, int, int]:
    total = len(questions)
    if total == 0:
        return 0.0, 0, 0

    correct = sum(1 for q in questions if _is_correct(q, answers.get(q["id"])))
    score = round(100 * correct / total, 2)
    return score, correct, total
