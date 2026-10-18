// Six named colours. Each is shown with a dot and its name, so colour is never
// the only cue. HIGHLIGHT_TINT is the share of the hue mixed over the page
// background; constants.test.js keeps body text at AA on every tint.
export const HIGHLIGHT_COLORS = [
  { id: "yellow", label: "Yellow", hue: "#f2c94c" },
  { id: "green", label: "Green", hue: "#6fcf97" },
  { id: "blue", label: "Blue", hue: "#56ccf2" },
  { id: "pink", label: "Pink", hue: "#f78fb3" },
  { id: "orange", label: "Orange", hue: "#f2994a" },
  { id: "purple", label: "Purple", hue: "#bb86fc" },
];

export const HIGHLIGHT_TINT = 0.35;
export const MAX_SELECTION = 2000;
export const MAX_COMMENT = 2000;

export const colorLabel = (id) => HIGHLIGHT_COLORS.find((c) => c.id === id)?.label ?? id;
