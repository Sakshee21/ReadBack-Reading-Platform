import { useSettings } from "../SettingsContext";
import AmbientSound from "./AmbientSound";

export default function SettingsPanel({ open, onClose, bookId = null }) {
  const {
    reduceMotion,
    setReduceMotion,
    motionFollowsSystem,
    resetMotionToSystem,
    plainTheme,
    setPlainTheme,
  } = useSettings();

  if (!open) return null;

  return (
    <div className="drawer-overlay" onClick={onClose}>
      <div className="settings-panel" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-header">
          <h2>Settings</h2>
          <button className="icon-btn" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="settings-body">
          <label className="settings-row">
            <input
              type="checkbox"
              checked={reduceMotion}
              onChange={(e) => setReduceMotion(e.target.checked)}
            />
            <span>Reduce motion</span>
          </label>
          <p className="settings-hint">
            Turns off fades, transitions and the celebration animation.
            {motionFollowsSystem
              ? " Currently following your system setting."
              : " "}
            {!motionFollowsSystem && (
              <button className="link-btn" onClick={resetMotionToSystem}>
                Follow system setting
              </button>
            )}
          </p>

          <label className="settings-row">
            <input
              type="checkbox"
              checked={plainTheme}
              onChange={(e) => setPlainTheme(e.target.checked)}
            />
            <span>Plain theme</span>
          </label>
          <p className="settings-hint">
            Ignores each book's background tint and uses the default palette.
          </p>

          <hr className="settings-divider" />

          <AmbientSound bookId={bookId} />
          <p className="settings-hint">
            Off by default. Starts only when you press play, and stops when you leave.
          </p>
        </div>
      </div>
    </div>
  );
}
