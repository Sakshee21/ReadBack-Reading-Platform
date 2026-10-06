# Credits and asset licences

Every third-party asset in this repo is listed here with its source and licence.
**Nothing with an unclear licence may be added.**

## Code dependencies (UI polish layer)

| Package | Version | Licence | Used for |
|---|---|---|---|
| [canvas-confetti](https://github.com/catdad/canvas-confetti) | 1.9.4 | ISC | Session-complete celebration burst |

Everything else in the motion/theming layer is hand-written CSS — no animation
library, no Lottie runtime.

## Book text

All book text comes from [Project Gutenberg](https://www.gutenberg.org/) and is
in the **public domain** in the United States. Text is downloaded at seed time
by `backend/scripts/import_book.py`; it is not committed to the repo.

## Visualization artwork — removed by design

There is none, deliberately. The "Picture this scene" checkpoint is
imagination-only: revealing a picture would supply the very imagery that
reading is meant to make the reader generate, which undercuts the dual-coding
rationale the project rests on. The image pipeline, manifest and curated
illustrations were removed in favour of an optional "how vivid was it?" rating.

## Ambient audio

All four loops were downloaded from [freesound.org](https://freesound.org) by
the project author.

| Served file | Source file | Size | Source |
|---|---|---|---|
| `rain.mp3` | `rain.wav` | 696 KB | freesound.org |
| `fire.mp3` | `fire.wav` | 1.2 MB | freesound.org |
| `ambient.mp3` | `ambient.wav` | 1.9 MB | freesound.org — `871734` by *zaamotek*, "mountain breathing" (acoustic guitar, dark ambient) |
| `ambient2.mp3` | `ambient2.wav` | 1.4 MB | freesound.org |

Freesound hosts files under several different licences (CC0, CC-BY, CC-BY-NC,
Sampling+). If any of the above turns out to be **CC-BY**, it needs the author
credited here; CC0 needs nothing. Worth a one-minute check on the download pages
before the project is submitted.

Requirements for any ambient file added later:

- Prefer **CC0**, or a licence that clearly permits redistribution in this repo.
- Avoid intelligible speech — it competes directly with reading.

### How the files are built

Source `.wav` uploads are tens of megabytes and are **gitignored**; only the
compressed `.mp3` loops are committed. Rebuild them with:

```bash
bash frontend/scripts/build_audio.sh    # needs ffmpeg
```

That script compresses to 96 kbps and crossfades the loop point by 1 s, so the
clip does not click when it repeats. It turned a 16 MB WAV into a 696 KB MP3
and a 28 MB WAV into 1.2 MB.

To add or rename a sound: drop the `.wav` in, add it to the `SOURCES` list in
`build_audio.sh`, run it, then add a row to `frontend/src/ambient.js` and to the
table above. The player, volume control, persistence and `ambient_sound_on/off`
logging pick it up automatically.
