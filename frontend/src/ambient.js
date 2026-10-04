/**
 * Ambient focus sounds.
 *
 * Files are served from frontend/public/audio/ and must be committed to the
 * repo - never hotlinked - and must be CC0 or similarly unambiguous. See
 * CREDITS.md for the required files and their licences.
 *
 * The files are NOT in the repo yet. Until they are, the player shows a clear
 * "file missing" hint instead of failing silently; dropping the files in at
 * these exact paths is all that's needed to switch it on.
 */

export const AMBIENT_SOUNDS = [
  { id: "none", label: "Off", src: null },
  { id: "rain", label: "Rain", src: "/audio/rain.mp3" },
  { id: "fireplace", label: "Fireplace", src: "/audio/fireplace.mp3" },
  { id: "cafe", label: "Soft cafe", src: "/audio/cafe.mp3" },
];

export function soundById(id) {
  return AMBIENT_SOUNDS.find((s) => s.id === id) || AMBIENT_SOUNDS[0];
}
