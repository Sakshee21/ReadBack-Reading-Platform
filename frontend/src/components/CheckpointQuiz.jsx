import { useEffect, useState } from "react";
import { api, logEvent } from "../api";

function questionType(q) {
  return q.question_type || q.type || "inference";
}

function isAnswered(q, answer) {
  const type = questionType(q);
  if (type === "sequencing") return Array.isArray(answer) && answer.length === q.items.length;
  if (type === "relationship") {
    return answer && q.left_items.every((item) => answer[item]);
  }
  return Boolean(answer);
}

/** Click items in story order; clicking a chosen item again removes it. */
function SequencingQuestion({ question, answer, onChange }) {
  const chosen = Array.isArray(answer) ? answer : [];

  function toggle(item) {
    onChange(chosen.includes(item) ? chosen.filter((i) => i !== item) : [...chosen, item]);
  }

  return (
    <div className="quiz-options">
      {question.items.map((item) => {
        const position = chosen.indexOf(item);
        return (
          <div
            key={item}
            className={`quiz-option sequencing ${position >= 0 ? "selected" : ""}`}
            onClick={() => toggle(item)}
          >
            <span className="seq-badge">{position >= 0 ? position + 1 : ""}</span>
            {item}
          </div>
        );
      })}
      <button type="button" className="btn-secondary" onClick={() => onChange([])}>
        Clear order
      </button>
    </div>
  );
}

function RelationshipQuestion({ question, answer, onChange }) {
  const current = answer || {};
  return (
    <div className="quiz-matches">
      {question.left_items.map((item) => (
        <label key={item} className="quiz-match-row">
          <span className="quiz-match-left">{item}</span>
          <select
            value={current[item] || ""}
            onChange={(e) => onChange({ ...current, [item]: e.target.value })}
          >
            <option value="">Choose...</option>
            {question.options.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
      ))}
    </div>
  );
}

function InferenceQuestion({ question, answer, onChange }) {
  return (
    <div className="quiz-options">
      {question.options.map((option) => (
        <div
          key={option}
          className={`quiz-option ${answer === option ? "selected" : ""}`}
          onClick={() => onChange(option)}
        >
          <input type="radio" checked={answer === option} readOnly />
          {option}
        </div>
      ))}
    </div>
  );
}

const TYPE_LABELS = {
  sequencing: "Put these in order",
  relationship: "Match them up",
  inference: "What does this suggest?",
};

export default function CheckpointQuiz({ checkpoint, onDone }) {
  const [answers, setAnswers] = useState({});
  const [result, setResult] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const questions = checkpoint.questions;
  const allAnswered = questions.every((q) => isAnswered(q, answers[q.id]));

  useEffect(() => {
    logEvent("quiz_started", {
      bookId: checkpoint.book_id,
      chapter_index_trigger: checkpoint.chapter_index_trigger,
      checkpoint_id: checkpoint.id,
      question_types: questions.map(questionType),
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [checkpoint.id]);

  function setAnswer(id, value) {
    setAnswers((a) => ({ ...a, [id]: value }));
  }

  async function handleSubmit() {
    setSubmitting(true);
    try {
      const res = await api.submitCheckpoint(checkpoint.id, answers);
      setResult(res);
      logEvent("quiz_submitted", {
        bookId: checkpoint.book_id,
        chapter_index_trigger: checkpoint.chapter_index_trigger,
        checkpoint_id: checkpoint.id,
        score: res.score,
        correct: res.correct,
        total: res.total,
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-overlay">
      <div className="checkpoint-card">
        {!result ? (
          <>
            <h2>Comprehension check</h2>
            <p className="subtitle">Answer these before continuing to the next chapter.</p>
            {questions.map((q) => {
              const type = questionType(q);
              return (
                <div className="quiz-question" key={q.id}>
                  <div className="quiz-type-label">{TYPE_LABELS[type] || "Question"}</div>
                  <div className="prompt">{q.prompt}</div>
                  {type === "sequencing" && (
                    <SequencingQuestion
                      question={q}
                      answer={answers[q.id]}
                      onChange={(v) => setAnswer(q.id, v)}
                    />
                  )}
                  {type === "relationship" && (
                    <RelationshipQuestion
                      question={q}
                      answer={answers[q.id]}
                      onChange={(v) => setAnswer(q.id, v)}
                    />
                  )}
                  {type !== "sequencing" && type !== "relationship" && (
                    <InferenceQuestion
                      question={q}
                      answer={answers[q.id]}
                      onChange={(v) => setAnswer(q.id, v)}
                    />
                  )}
                </div>
              );
            })}
            <button className="btn-primary" disabled={!allAnswered || submitting} onClick={handleSubmit}>
              {submitting ? "Submitting..." : "Submit answers"}
            </button>
          </>
        ) : (
          <div className="checkpoint-result">
            <h2>Nice work</h2>
            <div className="score">{result.score}%</div>
            <p>
              {result.correct} of {result.total} correct
            </p>
            <button className="btn-primary" onClick={() => onDone(result)}>
              Continue reading
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
