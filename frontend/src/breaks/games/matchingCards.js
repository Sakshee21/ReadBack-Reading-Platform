import { mulberry32, shuffle } from "../rng";

// Plain geometric glyphs, so the game stays non-verbal. `name` is for screen
// readers. Glyphs that some fonts draw as colour emoji carry U+FE0E to force
// text presentation; Dingbats are avoided because fonts cover them patchily.
export const SYMBOLS = [
  { glyph: "\u25CF", name: "circle" },
  { glyph: "\u25A0", name: "square" },
  { glyph: "\u25B2", name: "triangle" },
  { glyph: "\u25C6", name: "diamond" },
  { glyph: "\u2605\ufe0e", name: "star" },
  { glyph: "\u2665\uFE0E", name: "heart" },
  { glyph: "\u2663\uFE0E", name: "club" },
  { glyph: "\u2660\uFE0E", name: "spade" },
  { glyph: "\u263E", name: "moon" },
  { glyph: "\u2600\uFE0E", name: "sun" },
  { glyph: "\u25BC", name: "inverted triangle" },
  { glyph: "\u266A\uFE0E", name: "note" },
];

const PAIRS = 6;

export function generate(seed) {
  const rand = mulberry32(seed);
  const chosen = shuffle(SYMBOLS, rand).slice(0, PAIRS);
  const cards = shuffle([...chosen, ...chosen], rand).map((s) => ({ symbol: s.glyph, name: s.name }));
  return { cards };
}

export function initialState() {
  return { faceUp: [], matched: [], pending: null };
}

// Returns the same state object whenever the flip is ignored.
export function flip(puzzle, state, index) {
  if (!Number.isInteger(index) || index < 0 || index >= puzzle.cards.length) return state;
  if (state.pending || state.matched.includes(index) || state.faceUp.includes(index)) return state;

  const faceUp = [...state.faceUp, index];
  if (faceUp.length < 2) return { ...state, faceUp };

  const [a, b] = faceUp;
  if (puzzle.cards[a].symbol === puzzle.cards[b].symbol) {
    return { faceUp: [], matched: [...state.matched, a, b], pending: null };
  }
  return { ...state, faceUp, pending: [a, b] };
}

export function clearMismatch(state) {
  return state.pending ? { ...state, faceUp: [], pending: null } : state;
}

export function isComplete(puzzle, state) {
  return state.matched.length === puzzle.cards.length;
}

export function solve(puzzle) {
  return puzzle.cards.map((_, i) => i);
}
