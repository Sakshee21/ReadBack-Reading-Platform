import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useState } from "react";
import { applyTheme, normalizeAppearance, normalizePalette } from "./theme/appearance";
import { DEFAULT_PALETTE, SCHEME_IDS } from "./theme/schemes";

const STORAGE_KEY = "readback_settings";

const DEFAULTS = {
  // null = follow the OS "prefers-reduced-motion" setting until the user picks.
  reduceMotion: null,
  plainTheme: false,
  ambientId: "none",
  ambientVolume: 0.4,
  // Offer a short optional puzzle break after ~10 minutes of reading.
  offerBreaks: true,
  // Show the passage's theme tags under the text. Off unless the reader opts in.
  showThemeTags: false,
  // Appearance: "auto" keeps the stylesheet look (device mode + book tint).
  scheme: "auto",
  customPalette: DEFAULT_PALETTE,
};

function readStored() {
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
    return { ...DEFAULTS, ...stored, ...normalizeAppearance(stored) };
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

  // Before paint, so a change never shows a frame of the old colours.
  useLayoutEffect(() => {
    applyTheme(settings.scheme, settings.customPalette);
  }, [settings.scheme, settings.customPalette]);

  // One switch drives every animation in the app (see motion.css). Writing
  // "false" explicitly also lets a user who wants motion override the OS hint.
  useEffect(() => {
    document.documentElement.dataset.reduceMotion = reduceMotion ? "true" : "false";
  }, [reduceMotion]);

  // Another tab changed the settings: follow it, so two tabs never fight over the look.
  useEffect(() => {
    const onStorage = (e) => {
      if (e.key === STORAGE_KEY) setSettings(readStored());
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

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
      setOfferBreaks: (v) => update({ offerBreaks: v }),
      setShowThemeTags: (v) => update({ showThemeTags: v }),
      setScheme: (id) => {
        if (SCHEME_IDS.includes(id)) update({ scheme: id });
      },
      setCustomPalette: (palette) =>
        setSettings((s) => ({
          ...s,
          customPalette: normalizePalette({ ...s.customPalette, ...palette }),
        })),
      resetAppearance: () => update({ scheme: "auto", customPalette: DEFAULT_PALETTE }),
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
