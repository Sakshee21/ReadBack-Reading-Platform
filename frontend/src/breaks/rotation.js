import { shuffle } from "./rng";

const DEFAULT_KEY = "readback_break_rotation";

function load(storage, key) {
  try {
    const parsed = JSON.parse(storage.getItem(key));
    if (parsed && Array.isArray(parsed.bag)) {
      return { bag: parsed.bag, last: typeof parsed.last === "string" ? parsed.last : null };
    }
  } catch {
    // unreadable storage behaves like an empty bag
  }
  return { bag: [], last: null };
}

// Shuffled-bag rotation: every game plays once before any game repeats, and a
// refill never starts with the game that just played. The reader never chooses.
export function nextGameId(ids, storage, rand, key = DEFAULT_KEY) {
  const state = load(storage, key);
  let bag = state.bag.filter((id) => ids.includes(id));

  if (bag.length === 0) {
    bag = shuffle(ids, rand);
    if (ids.length > 1 && bag[0] === state.last) bag.push(bag.shift());
  }

  const id = bag.shift();
  try {
    storage.setItem(key, JSON.stringify({ bag, last: id }));
  } catch {
    // storage unavailable - rotation just won't survive a reload
  }
  return id;
}
