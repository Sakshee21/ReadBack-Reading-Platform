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

## Visualization artwork

Illustrations are listed in `backend/data/visualization_manifest.json`, each with
its own `source_url`, `attribution` and `license` field. Currently applied:

| Source | Licence | Notes |
|---|---|---|
| True Williams illustrations for *The Adventures of Tom Sawyer* (1876), via the Project Gutenberg edition of book #74 | Public domain | 3 images applied; 42 more auto-matched and awaiting human review |

Downloaded image files live in `backend/static/visualizations/` and are
gitignored — they rebuild from the manifest with
`python -m scripts.visualization_images --apply`.

## Ambient audio — **NOT YET SUPPLIED**

The ambient sound player is fully built and wired, but **the audio files are not
in the repo**. The UI shows a "file not found" hint until they are added.

To enable it, drop these files into `frontend/public/audio/`:

| File | Suggested content | Requirements |
|---|---|---|
| `rain.mp3` | Steady rain, no thunder | seamless loop, mono or stereo, ~128 kbps, under ~1.5 MB |
| `fireplace.mp3` | Crackling fire | seamless loop, same budget |
| `cafe.mp3` | Low cafe murmur, no intelligible speech | seamless loop, same budget |

Rules for choosing them:

- **CC0 / public domain only** (or a licence that unambiguously permits
  redistribution in this repo). Good sources: freesound.org filtered to CC0,
  Pixabay, or any recording you made yourself.
- Avoid anything with music, lyrics, or recognisable speech — it competes with
  reading.
- Loop cleanly: a click or gap at the seam is very noticeable at low volume.
- **Record each file in the table below once added**, with the source URL,
  author and licence.

| File | Source URL | Author | Licence |
|---|---|---|---|
| `rain.mp3` | _TODO_ | _TODO_ | _TODO_ |
| `fireplace.mp3` | _TODO_ | _TODO_ | _TODO_ |
| `cafe.mp3` | _TODO_ | _TODO_ | _TODO_ |

To add or rename sounds, edit `frontend/src/ambient.js` — the player, volume
control, persistence and `ambient_sound_on/off` logging all pick them up
automatically.
