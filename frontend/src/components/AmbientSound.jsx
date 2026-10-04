import { useEffect, useRef, useState } from "react";
import { AMBIENT_SOUNDS, soundById } from "../ambient";
import { logEvent } from "../api";
import { useSettings } from "../SettingsContext";

/**
 * Optional looping focus sound. Off by default and never auto-started: a
 * browser would block that anyway, and more importantly it should be the
 * reader's choice. Playback is entirely separate from reading-session timing -
 * it logs its own events and touches nothing else.
 */
export default function AmbientSound({ bookId = null }) {
  const { ambientId, ambientVolume, setAmbientId, setAmbientVolume } = useSettings();
  const [playing, setPlaying] = useState(false);
  const [missing, setMissing] = useState(false);
  const audioRef = useRef(null);

  // Keep volume live while dragging the slider.
  useEffect(() => {
    if (audioRef.current) audioRef.current.volume = ambientVolume;
  }, [ambientVolume]);

  // Stop cleanly when the component goes away or the page is closed.
  useEffect(() => {
    const stop = () => {
      const el = audioRef.current;
      if (el) {
        el.pause();
        el.src = "";
      }
    };
    window.addEventListener("pagehide", stop);
    return () => {
      window.removeEventListener("pagehide", stop);
      stop();
    };
  }, []);

  function stop(logIt = true) {
    const el = audioRef.current;
    if (el) el.pause();
    setPlaying(false);
    if (logIt) logEvent("ambient_sound_off", { bookId, sound_id: ambientId });
  }

  async function play(id) {
    const sound = soundById(id);
    if (!sound.src) return;

    let el = audioRef.current;
    if (!el) {
      el = new Audio();
      el.loop = true;
      audioRef.current = el;
    }
    if (el.getAttribute("data-sound") !== id) {
      el.src = sound.src;
      el.setAttribute("data-sound", id);
    }
    el.volume = ambientVolume;

    try {
      await el.play(); // must be inside a user gesture
      setMissing(false);
      setPlaying(true);
      logEvent("ambient_sound_on", { bookId, sound_id: id, volume: ambientVolume });
    } catch {
      // Missing file, unsupported codec, or a blocked gesture.
      setMissing(true);
      setPlaying(false);
    }
  }

  function handleSelect(id) {
    const wasPlaying = playing;
    if (wasPlaying) stop(true);
    setAmbientId(id);
    setMissing(false);
    if (id !== "none" && wasPlaying) play(id);
  }

  const current = soundById(ambientId);

  return (
    <div className="ambient-control">
      <label className="settings-row">
        <span>Ambient sound</span>
        <select value={ambientId} onChange={(e) => handleSelect(e.target.value)}>
          {AMBIENT_SOUNDS.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
        </select>
      </label>

      {current.src && (
        <>
          <div className="settings-row">
            <button
              className="btn-secondary"
              onClick={() => (playing ? stop() : play(ambientId))}
            >
              {playing ? "Stop" : "Play"}
            </button>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={ambientVolume}
              aria-label="Ambient volume"
              onChange={(e) => setAmbientVolume(Number(e.target.value))}
            />
            <span className="settings-hint">{Math.round(ambientVolume * 100)}%</span>
          </div>
          {missing && (
            <p className="settings-warning">
              Audio file not found at <code>{current.src}</code>. See CREDITS.md for the
              CC0 files to drop into <code>frontend/public/audio/</code>.
            </p>
          )}
        </>
      )}
    </div>
  );
}
