export default function StreakDisplay({ streak }) {
  if (!streak) return null;
  return (
    <div className="streak-badge">
      <span className="flame">{streak.current_streak > 0 ? "🔥" : "💤"}</span>
      <div className="streak-numbers">
        <span className="streak-current">
          {streak.current_streak} day{streak.current_streak === 1 ? "" : "s"}
        </span>
        <span className="streak-longest">Best: {streak.longest_streak}</span>
      </div>
    </div>
  );
}
