"""Load the shipped theme tags into the database.

Normally this happens automatically at the end of `python -m scripts.seed_books`.
Run it by hand to load a file again. Tags are permanent: chunks that already
have tags are left exactly as they are, so this is safe to repeat.

Usage:
    python -m scripts.import_theme_tags                 # backend/data/theme_tags.json
    python -m scripts.import_theme_tags --file tags.json
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal  # noqa: E402
from app.services import theme_seed  # noqa: E402


def report(summary: dict) -> str:
    return (
        f"Theme tags: imported {summary['imported']}, already had tags {summary['skipped_existing']}, "
        f"text changed {summary['mismatched']}, invalid {summary['invalid']}, "
        f"books not found {summary['missing_books']}"
    )


def main(argv=None) -> dict:
    parser = argparse.ArgumentParser(description="Import shipped theme tags.")
    parser.add_argument("--file", default=str(theme_seed.DEFAULT_PATH))
    args = parser.parse_args(argv)
    db = SessionLocal()
    try:
        summary = theme_seed.import_file(db, Path(args.file))
    finally:
        db.close()
    if summary is None:
        print(f"No such file: {args.file}", file=sys.stderr)
        return {"error": "no such file"}
    print(report(summary))
    return summary


if __name__ == "__main__":
    result = main()
    sys.exit(1 if "error" in result else 0)
