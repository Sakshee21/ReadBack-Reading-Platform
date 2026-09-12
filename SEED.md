# Seeding the database

The seed script pulls 5 public-domain books from Project Gutenberg, runs them through
the content pipeline (boilerplate stripping -> chapter splitting -> micro-session
splitting), and attaches hand-authored recap summaries and comprehension checkpoints
where provided.

## Run it

```bash
cd backend
source .venv/Scripts/activate
alembic upgrade head        # make sure the schema exists first
python -m scripts.seed_books
```

Safe to re-run: books already imported (matched by `gutenberg_id`) are skipped.

## What gets seeded

| Book | Gutenberg ID | Chapters | Chapter summaries | Checkpoint |
|---|---|---|---|---|
| The Yellow Wallpaper | 1952 | 1 | Hand-written | - |
| Alice's Adventures in Wonderland | 11 | 12 | Hand-written (1-9) | Ch. 10, 3 questions |
| The Adventures of Tom Sawyer | 74 | 35 | Naive fallback | Ch. 10, 3 questions |
| Frankenstein | 84 | 25 (incl. framing letters) | Naive fallback | Ch. 5, 3 questions |
| Pride and Prejudice | 1342 | 62 (incl. preface) | Naive fallback | Ch. 15, 3 questions |

"Naive fallback" means the recap engine uses the chapter's first 1-2 sentences
(`app/services/summarize.py`) instead of a hand-written summary - simple and
deterministic, per the MVP scope (no LLM calls). Swap in real summaries any time by
adding entries to that book's `chapter_summaries` dict in `scripts/seed_books.py` and
re-seeding (see "Resetting" below).

## Importing another book

```bash
python -m scripts.import_book <gutenberg_id>
```

Find IDs at https://www.gutenberg.org or https://gutendex.com. After importing, add a
manual spot-check: open `/books` in the API and confirm the chapter count and first
chapter's title look right (see the "known simplifications" note in the root README
about the chapter-detection heuristic). Chapter summaries and comprehension checkpoints
for a new book aren't generated automatically - add them the same way `seed_books.py`
does, using `ComprehensionCheckpoint` rows and the `Chapter.summary` field.

## Resetting the database

To wipe and reseed from scratch (e.g. after changing the segmentation pipeline):

```bash
alembic downgrade base
alembic upgrade head
python -m scripts.seed_books
```

This drops all tables (users included), so only do this in development.
