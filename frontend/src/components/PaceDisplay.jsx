const TREND_MARK = { faster: "↑", slower: "↓", steady: "→" };

function formatMinutes(minutes) {
  if (minutes === null || minutes === undefined) return null;
  if (minutes < 60) return `${Math.round(minutes)} min`;
  const hours = Math.floor(minutes / 60);
  const rest = Math.round(minutes % 60);
  return rest ? `${hours}h ${rest}m` : `${hours}h`;
}

export default function PaceDisplay({ pace }) {
  if (!pace || !pace.wpm_average) return null;

  const left = formatMinutes(pace.minutes_left_book);
  return (
    <div className="pace-badge" title={`Based on ${pace.sessions_counted} recent session(s)`}>
      <span className="pace-wpm">
        {Math.round(pace.wpm_average)} wpm
        <span className={`pace-trend ${pace.trend}`}>{TREND_MARK[pace.trend]}</span>
      </span>
      {left && <span className="pace-left">{left} left</span>}
    </div>
  );
}
