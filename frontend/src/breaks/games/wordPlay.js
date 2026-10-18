import { mulberry32, shuffle } from "../rng";
import { ANAGRAMS, LADDERS, WORDS } from "./wordData";

const WORD_SET = new Set(WORDS);

export function normalize(input) {
  return String(input ?? "").trim().toLowerCase();
}

export function differsByOne(a, b) {
  if (a.length !== b.length) return false;
  let diffs = 0;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) diffs++;
  return diffs === 1;
}

// Breadth-first search over the bundled word list, inclusive of both ends.
// Words in `avoid` are treated as already used and are never stepped onto.
export function shortestPath(from, to, avoid = new Set()) {
  if (!WORD_SET.has(from) || !WORD_SET.has(to)) return null;
  if (from === to) return [from];
  const previous = new Map([[from, null]]);
  const queue = [from];
  while (queue.length) {
    const word = queue.shift();
    for (const next of WORDS) {
      if (previous.has(next) || avoid.has(next) || !differsByOne(word, next)) continue;
      previous.set(next, word);
      if (next === to) {
        const path = [to];
        for (let w = word; w !== null; w = previous.get(w)) path.unshift(w);
        return path;
      }
      queue.push(next);
    }
  }
  return null;
}

function scramble(word, rand) {
  for (let attempt = 0; attempt < 20; attempt++) {
    const letters = shuffle([...word], rand).join("");
    if (letters !== word) return letters;
  }
  return word.slice(1) + word[0];
}

// Even seeds give a word ladder, odd seeds an anagram. The seed is logged with
// break_game_start, so the variant is recoverable from the event log.
export function generate(seed) {
  const rand = mulberry32(seed);
  if (seed % 2 === 0) {
    const { start, target } = LADDERS[Math.floor(rand() * LADDERS.length)];
    return { kind: "ladder", start, target, path: shortestPath(start, target) };
  }
  const word = ANAGRAMS[Math.floor(rand() * ANAGRAMS.length)];
  return { kind: "anagram", word, scrambled: scramble(word, rand) };
}

export function tryStep(puzzle, chain, input) {
  const word = normalize(input);
  if (word.length !== puzzle.start.length) return { ok: false, reason: "length" };
  if (!WORD_SET.has(word)) return { ok: false, reason: "not_a_word" };
  if (chain.includes(word)) return { ok: false, reason: "repeat" };
  if (!differsByOne(chain[chain.length - 1], word)) return { ok: false, reason: "not_one_letter" };
  return { ok: true, chain: [...chain, word], solved: word === puzzle.target };
}

export function checkAnagram(puzzle, input) {
  const word = normalize(input);
  return word.length > 0 && word === puzzle.word;
}

// Ladder hints skip every word already in the chain; null means there is no way
// forward from here (the player can undo the last word).
export function hint(puzzle, chain) {
  if (puzzle.kind === "anagram") return puzzle.word[0];
  const used = chain && chain.length ? chain : [puzzle.start];
  const last = used[used.length - 1];
  const path = shortestPath(last, puzzle.target, new Set(used.slice(0, -1)));
  return path && path.length > 1 ? path[1] : null;
}

export function solve(puzzle) {
  return puzzle.kind === "ladder" ? puzzle.path : puzzle.word;
}
