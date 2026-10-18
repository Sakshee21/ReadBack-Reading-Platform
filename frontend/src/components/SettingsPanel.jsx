import { useEffect, useRef, useState } from "react";
import { useSettings } from "../SettingsContext";
import { logEvent } from "../api";
import { DEFAULT_PALETTE, SCHEMES, checkPalette } from "../theme/schemes";
import AmbientSound from "./AmbientSound";

const SCHEME_OPTIONS = [
  { id: "auto", label: "Automatic", swatch: ["#f7f3ea", "#1c1a17"] },
  { id: "light", label: "Light", swatch: [SCHEMES.light.bg, SCHEMES.light.accent] },
  { id: "dark", label: "Dark", swatch: [SCHEMES.dark.bg, SCHEMES.dark.accent] },
  { id: "contrast", label: "Black and white", swatch: ["#ffffff", "#000000"] },
  { id: "custom", label: "Custom", swatch: null },
];

const PALETTE_FIELDS = [
  ["bg", "Background"],
  ["surface", "Cards"],
  ["text", "Text"],
  ["accent", "Accent"],
];

const PALETTE_LOG_DELAY_MS = 800;

export default function SettingsPanel({ open, onClose, bookId = null }) {
  const {
    reduceMotion,
    setReduceMotion,
    motionFollowsSystem,
    resetMotionToSystem,
    plainTheme,
    setPlainTheme,
    offerBreaks,
    setOfferBreaks,
    scheme,
    setScheme,
    customPalette,
    setCustomPalette,
    resetAppearance,
  } = useSettings();

  // The pickers show what the reader chose even when a value was refused.
  const [draft, setDraft] = useState(customPalette);
  // Show what is really applied whenever the panel opens or the theme changes,
  // not a refused colour left over from an earlier edit.
  useEffect(() => {
    setDraft(customPalette);
  }, [open, scheme, customPalette]);
  const logTimer = useRef(null);
  const pendingLog = useRef(null);

  // Send a palette edit that is still waiting out its debounce.
  const flushPaletteLog = () => {
    clearTimeout(logTimer.current);
    if (pendingLog.current) {
      logEvent("theme_changed", pendingLog.current);
      pendingLog.current = null;
    }
  };
  const flushRef = useRef(flushPaletteLog);
  flushRef.current = flushPaletteLog;
  useEffect(() => () => flushRef.current(), []);

  const check = checkPalette(draft);

  const chooseScheme = (id) => {
    flushPaletteLog();
    setScheme(id);
    logEvent("theme_changed", { scheme: id });
  };

  const editColor = (key, value) => {
    const next = { ...draft, [key]: value };
    setDraft(next);
    const result = checkPalette(next);
    if (result.level !== "refuse") setCustomPalette(next);
    clearTimeout(logTimer.current);
    pendingLog.current = {
      scheme: "custom",
      ...next,
      text_on_bg: Math.round(result.textOnBg * 100) / 100,
      level: result.level,
    };
    logTimer.current = setTimeout(flushPaletteLog, PALETTE_LOG_DELAY_MS);
  };

  const reset = () => {
    clearTimeout(logTimer.current);
    pendingLog.current = null;
    resetAppearance();
    setDraft(DEFAULT_PALETTE);
    logEvent("theme_changed", { scheme: "auto", reset: true });
  };

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
          <fieldset className="appearance-group">
            <legend>Theme</legend>
            {SCHEME_OPTIONS.map((o) => (
              <label key={o.id} className="settings-row appearance-option">
                <input
                  type="radio"
                  name="theme"
                  checked={scheme === o.id}
                  onChange={() => chooseScheme(o.id)}
                />
                <span
                  className="appearance-swatch"
                  aria-hidden="true"
                  style={
                    o.swatch
                      ? { background: `linear-gradient(90deg, ${o.swatch[0]} 50%, ${o.swatch[1]} 50%)` }
                      : { background: `linear-gradient(90deg, ${draft.bg} 33%, ${draft.text} 33% 66%, ${draft.accent} 66%)` }
                  }
                />
                <span>{o.label}</span>
              </label>
            ))}
          </fieldset>
          <p className="settings-hint">Anything other than Automatic turns off each book's colours.</p>

          {scheme === "custom" && (
            <div className="appearance-custom">
              {PALETTE_FIELDS.map(([key, label]) => (
                <label key={key} className="appearance-picker">
                  <span>{label}</span>
                  <input type="color" value={draft[key]} onChange={(e) => editColor(key, e.target.value)} />
                </label>
              ))}
              <p role="status" className={`appearance-status appearance-${check.level}`}>
                {check.message}
              </p>
              <p className="appearance-ratio">
                Text on {check.worst.pair} {check.worst.ratio.toFixed(1)} to 1
              </p>
            </div>
          )}
          <button type="button" className="btn-secondary" onClick={reset}>
            Reset appearance
          </button>

          <hr className="settings-divider" />

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
              disabled={scheme !== "auto"}
              aria-describedby="plain-theme-hint"
              onChange={(e) => setPlainTheme(e.target.checked)}
            />
            <span>Plain theme</span>
          </label>
          <p className="settings-hint" id="plain-theme-hint">
            Ignores each book's background tint and uses the default palette. Only used with Automatic.
          </p>

          <label className="settings-row">
            <input
              type="checkbox"
              checked={offerBreaks}
              onChange={(e) => setOfferBreaks(e.target.checked)}
            />
            <span>Offer short breaks</span>
          </label>
          <p className="settings-hint">
            After about 10 minutes of reading, offer an optional 2-minute puzzle. Never during a passage.
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
