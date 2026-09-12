import { useState } from "react";
import { api } from "../api";

export default function CheckpointQuiz({ checkpoint, onDone }) {
  const [answers, setAnswers] = useState({});
  const [result, setResult] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const questions = checkpoint.questions;
  const allAnswered = questions.every((q) => answers[q.id]);

  async function handleSubmit() {
    setSubmitting(true);
    try {
      const res = await api.submitCheckpoint(checkpoint.id, answers);
      setResult(res);
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
            {questions.map((q) => (
              <div className="quiz-question" key={q.id}>
                <div className="prompt">{q.prompt}</div>
                <div className="quiz-options">
                  {q.options.map((option) => (
                    <div
                      key={option}
                      className={`quiz-option ${answers[q.id] === option ? "selected" : ""}`}
                      onClick={() => setAnswers((a) => ({ ...a, [q.id]: option }))}
                    >
                      <input type="radio" checked={answers[q.id] === option} readOnly />
                      {option}
                    </div>
                  ))}
                </div>
              </div>
            ))}
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
