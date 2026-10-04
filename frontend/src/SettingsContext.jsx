import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

const STORAGE_KEY = "readback_settings";

const DEFAULTS = {
  // null = follow the OS "prefers-reduced-motion" setting until the user picks.
  reduceMotion: null,
  plainTheme: false,
  ambientId: "none",
  ambientVolume: 0.4,
};

function readStored() {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}") };
  } catch {
    return { ...DEFAULTS };
  }
}

function systemPrefersReducedMotion() {
  return (
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true
  );
}

const SettingsContext = createContext(null);

export function SettingsProvider({ children }) {
  const [settings, setSettings] = useState(readStored);
  const [systemReduce, setSystemReduce] = useState(systemPrefersReducedMotion);

  // Follow the OS setting live, as long as the user hasn't chosen explicitly.
  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!mq) return;
    const onChange = (e) => setSystemReduce(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    } catch {
      // private mode / storage disabled - settings just won't persist
    }
  }, [settings]);

  const reduceMotion = settings.reduceMotion ?? systemReduce;

  // One switch drives every animation in the app (see motion.css). Writing
  // "false" explicitly also lets a user who wants motion override the OS hint.
  useEffect(() => {
    document.documentElement.dataset.reduceMotion = reduceMotion ? "true" : "false";
  }, [reduceMotion]);

  const update = useCallback((patch) => setSettings((s) => ({ ...s, ...patch })), []);

  const value = useMemo(
    () => ({
      ...settings,
      reduceMotion,
      motionFollowsSystem: settings.reduceMotion === null,
      setReduceMotion: (v) => update({ reduceMotion: v }),
      setPlainTheme: (v) => update({ plainTheme: v }),
      setAmbientId: (v) => update({ ambientId: v }),
      setAmbientVolume: (v) => update({ ambientVolume: v }),
      resetMotionToSystem: () => update({ reduceMotion: null }),
    }),
    [settings, reduceMotion, update]
  );

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}

export function useSettings() {
  const ctx = useContext(SettingsContext);
  if (!ctx) throw new Error("useSettings must be used within SettingsProvider");
  return ctx;
}
