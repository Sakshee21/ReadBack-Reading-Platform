export default function RecapBanner({ recap, onDismiss }) {
  if (!recap) return null;
  return (
    <div className="recap-banner">
      <div className="recap-label">Previously</div>
      <p>{recap.replace(/^Previously\.\.\.\s*/, "")}</p>
      {onDismiss && (
        <button className="recap-dismiss" onClick={onDismiss} aria-label="Dismiss recap">
          Dismiss
        </button>
      )}
    </div>
  );
}
