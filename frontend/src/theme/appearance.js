import { luminance, parseHex } from "./colors";
import { DEFAULT_PALETTE, SCHEME_IDS, VAR_MAP, schemePalette } from "./schemes";

export const STORAGE_KEY = "readback_settings";

export function normalizePalette(raw) {
  const src = raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {};
  const out = {};
  for (const key of Object.keys(DEFAULT_PALETTE)) {
    out[key] = parseHex(src[key]) || DEFAULT_PALETTE[key];
  }
  return out;
}

export function normalizeAppearance(raw) {
  const src = raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {};
  return {
    scheme: SCHEME_IDS.includes(src.scheme) ? src.scheme : "auto",
    customPalette: normalizePalette(src.customPalette),
  };
}

export function applyTheme(scheme, customPalette, root = document.documentElement) {
  const palette = schemePalette(scheme, normalizePalette(customPalette));
  if (!palette) {
    for (const v of Object.values(VAR_MAP)) root.style.removeProperty(v);
    root.style.removeProperty("color-scheme");
    root.setAttribute("data-scheme", "auto");
    return;
  }
  for (const [key, cssVar] of Object.entries(VAR_MAP)) root.style.setProperty(cssVar, palette[key]);
  root.style.setProperty("color-scheme", luminance(palette.bg) < 0.4 ? "dark" : "light");
  root.setAttribute("data-scheme", scheme);
}

export function applyStoredTheme(storage, root = document.documentElement) {
  try {
    const store = storage || window.localStorage;
    const raw = store.getItem(STORAGE_KEY);
    if (!raw) return;
    const { scheme, customPalette } = normalizeAppearance(JSON.parse(raw));
    applyTheme(scheme, customPalette, root);
  } catch {
    // Storage unavailable or corrupt: leave the page on its default look.
  }
}
