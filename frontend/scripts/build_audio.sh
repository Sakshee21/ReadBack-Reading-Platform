#!/usr/bin/env bash
#
# Build the ambient loops that the app actually serves.
#
# Source .wav files are large (tens of MB) and are NOT committed - only the
# small .mp3 output is. Re-run this after adding or replacing a source file:
#
#     bash frontend/scripts/build_audio.sh
#
# Needs ffmpeg (sudo apt install ffmpeg).
#
# Seamless looping: a raw clip clicks audibly when it repeats, because the
# waveform jumps. We take everything from CF seconds onward and crossfade it
# with the first CF seconds, so the clip ends sounding like its own opening and
# restarts at the CF mark - continuous across the loop point.
set -e

AUDIO_DIR="$(cd "$(dirname "$0")/../public/audio" && pwd)"
cd "$AUDIO_DIR"

CF=1.0        # crossfade length, seconds
BITRATE=96k   # plenty for background noise; keeps files ~1MB

# source .wav -> served .mp3
SOURCES=(
  "rain.wav:rain.mp3"
  "fire.wav:fire.mp3"
  "ambient.wav:ambient.mp3"
  "ambient2.wav:ambient2.mp3"
)

for pair in "${SOURCES[@]}"; do
  src="${pair%%:*}"
  out="${pair##*:}"
  if [ ! -f "$src" ]; then
    echo "skip $src (not present)"
    continue
  fi
  ffmpeg -v error -y -i "$src" -filter_complex \
    "[0:a]asplit=2[a][b];\
     [a]atrim=0:${CF},asetpts=N/SR/TB[ah];\
     [b]atrim=${CF},asetpts=N/SR/TB[bb];\
     [bb][ah]acrossfade=d=${CF}:c1=tri:c2=tri[out]" \
    -map "[out]" -c:a libmp3lame -b:a "$BITRATE" -ar 44100 -ac 2 "$out"
  printf '%-12s -> %-12s %s\n' "$src" "$out" "$(du -h "$out" | cut -f1)"
done

echo "Done. Remember to record each source and licence in CREDITS.md."
