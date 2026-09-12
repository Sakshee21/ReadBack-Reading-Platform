export default function RecapBanner({ recap }) {
  if (!recap) return null;
  return (
    <div className="recap-banner">
      <div className="recap-label">Previously</div>
      <p>{recap.replace(/^Previously\.\.\.\s*/, "")}</p>
    </div>
  );
}
