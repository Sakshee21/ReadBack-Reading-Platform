import { contrast, luminance, mix, readableOn } from "./colors";

export const SCHEME_IDS = ["auto", "light", "dark", "contrast", "custom"];

export const VAR_MAP = {
  bg: "--bg",
  surface: "--surface",
  text: "--text",
  textMuted: "--text-muted",
  accent: "--accent",
  accentHover: "--accent-hover",
  border: "--border",
  danger: "--danger",
  success: "--success",
  shadow: "--shadow",
  onAccent: "--on-accent",
};

export const SCHEMES = {
  light: {
    bg: "#f7f3ea", surface: "#ffffff", text: "#2b2622", textMuted: "#6b6258",
    accent: "#a8562f", accentHover: "#8c4523", border: "#e2d9c8",
    danger: "#b3413a", success: "#3f7a4d",
    shadow: "0 2px 10px rgba(0, 0, 0, 0.06)", onAccent: "#ffffff",
  },
  dark: {
    bg: "#1c1a17", surface: "#262320", text: "#ece6d9", textMuted: "#a89e8d",
    accent: "#d98354", accentHover: "#e69a6e", border: "#3a352e",
    danger: "#e5736b", success: "#6fbf84",
    shadow: "0 2px 14px rgba(0, 0, 0, 0.4)", onAccent: "#1c1a17",
  },
  contrast: {
    bg: "#ffffff", surface: "#ffffff", text: "#000000", textMuted: "#404040",
    accent: "#000000", accentHover: "#333333", border: "#000000",
    danger: "#b00020", success: "#1b5e20",
    shadow: "none", onAccent: "#ffffff",
  },
};

export const DEFAULT_PALETTE = {
  bg: SCHEMES.light.bg,
  surface: SCHEMES.light.surface,
  text: SCHEMES.light.text,
  accent: SCHEMES.light.accent,
};

const STATUS_LIGHT = { danger: "#b3413a", success: "#3f7a4d" };
const STATUS_DARK = { danger: "#e5736b", success: "#6fbf84" };

function minContrast(color, ...backgrounds) {
  return Math.min(...backgrounds.map((b) => contrast(color, b)));
}

export function derivePalette({ bg, surface, text, accent }) {
  // Muted text: move from a soft blend toward the text colour until legible.
  let textMuted = text;
  for (let t = 0.65; t <= 1.0001; t += 0.05) {
    const c = mix(bg, text, t);
    if (minContrast(c, bg, surface) >= 4.5) {
      textMuted = c;
      break;
    }
  }
  const score = (s) => minContrast(s.danger, bg, surface) + minContrast(s.success, bg, surface);
  const status = score(STATUS_LIGHT) >= score(STATUS_DARK) ? STATUS_LIGHT : STATUS_DARK;
  const dark = luminance(bg) < 0.4;
  const onAccent = readableOn(accent);
  return {
    bg,
    surface,
    text,
    textMuted,
    accent,
    // Move away from the on-accent text colour so hover keeps its contrast.
    accentHover: mix(accent, onAccent === "#ffffff" ? "#000000" : "#ffffff", 0.15),
    border: mix(bg, text, 0.15),
    danger: status.danger,
    success: status.success,
    shadow: dark ? SCHEMES.dark.shadow : SCHEMES.light.shadow,
    onAccent,
  };
}

export function checkPalette({ bg, surface, text, accent }) {
  const textOnBg = contrast(text, bg);
  const textOnSurface = contrast(text, surface);
  const accentOnBg = contrast(accent, bg);
  const accentOnSurface = contrast(accent, surface);
  const textMin = Math.min(textOnBg, textOnSurface);
  const worst =
    textOnBg <= textOnSurface
      ? { pair: "background", ratio: textOnBg }
      : { pair: "cards", ratio: textOnSurface };
  let level = "ok";
  let message = "Looks good";
  if (textMin < 3) {
    level = "refuse";
    message = "Too low to use: text needs at least 3 to 1 contrast, so this was not applied";
  } else if (textMin < 4.5) {
    level = "warn";
    message = "Low contrast: text may be hard to read";
  } else if (Math.min(accentOnBg, accentOnSurface) < 3) {
    level = "warn";
    message = "Low contrast: the accent colour may be hard to see";
  }
  return { textOnBg, textOnSurface, accentOnBg, accentOnSurface, worst, level, message };
}

export function schemePalette(schemeId, customPalette) {
  if (schemeId === "light" || schemeId === "dark" || schemeId === "contrast") return SCHEMES[schemeId];
  if (schemeId === "custom") return derivePalette(customPalette);
  return null;
}
