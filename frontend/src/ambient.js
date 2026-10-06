/**
 * Ambient focus sounds.
 *
 * Files are served from frontend/public/audio/ and must be committed to the
 * repo - never hotlinked - and must be CC0 or similarly unambiguous. Record
 * every file's source and licence in CREDITS.md.
 *
 * The .mp3 files here are built from the source .wav uploads by
 * scripts/build_audio.sh, which compresses them and crossfades the loop point
 * so there is no click on repeat. Re-run it after adding or replacing a .wav.
 *
 * Adding a sound: drop the .wav in, add it to build_audio.sh, run it, then add
 * a row here and in CREDITS.md. The player, volume, persistence and
 * ambient_sound_on/off logging all pick it up automatically.
 */

export const AMBIENT_SOUNDS = [
  { id: "none", label: "Off", src: null },
  { id: "rain", label: "Rain", src: "/audio/rain.mp3" },
  { id: "fire", label: "Fireplace", src: "/audio/fire.mp3" },
  { id: "ambient", label: "Ambient 1", src: "/audio/ambient.mp3" },
  { id: "ambient2", label: "Ambient 2", src: "/audio/ambient2.mp3" },
];

export function soundById(id) {
  return AMBIENT_SOUNDS.find((s) => s.id === id) || AMBIENT_SOUNDS[0];
}
