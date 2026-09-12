"""Scoring for comprehension checkpoint quizzes.

Each question in ComprehensionCheckpoint.questions is a dict:
{"id": "q1", "type": "timeline"|"character"|"inference", "prompt": str,
 "options": [str, ...], "answer": str}
Answers are matched case-insensitively against the stored `answer` field.
"""


def score_attempt(questions: list[dict], answers: dict[str, str]) -> tuple[float, int, int]:
    total = len(questions)
    if total == 0:
        return 0.0, 0, 0

    correct = 0
    for question in questions:
        qid = question["id"]
        given = (answers.get(qid) or "").strip().lower()
        expected = (question.get("answer") or "").strip().lower()
        if given and given == expected:
            correct += 1

    score = round(100 * correct / total, 2)
    return score, correct, total
