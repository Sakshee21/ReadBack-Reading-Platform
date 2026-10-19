"""Write the finished theme tags of the seeded books to a JSON file in the repo.

The file is imported when the books are seeded (scripts.seed_books), so a fresh
install has the tags without calling a model. Commit the file with the code.

Usage:
    python -m scripts.export_theme_tags                 # backend/data/theme_tags.json
    python -m scripts.export_theme_tags --out tags.json
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal  # noqa: E402
from app.services import theme_seed  # noqa: E402


def main(argv=None) -> dict:
    parser = argparse.ArgumentParser(description="Export seeded books' theme tags to a JSON file.")
    parser.add_argument("--out", default=str(theme_seed.DEFAULT_PATH))
    args = parser.parse_args(argv)
    db = SessionLocal()
    try:
        data = theme_seed.export_tags(db)
    finally:
        db.close()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(theme_seed.dumps(data), encoding="utf8")
    chunks = sum(len(b["chunks"]) for b in data["books"])
    models = sorted({c["model"] for b in data["books"] for c in b["chunks"]})
    print(f"Wrote {chunks} tagged chunks from {len(data['books'])} books to {out} (models: {', '.join(models) or 'none'})")
    return {"books": len(data["books"]), "chunks": chunks}


if __name__ == "__main__":
    main()
