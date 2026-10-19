"""Run two models over the same sampled chunks and compare their theme tags.

Nothing is stored in the database: this is for choosing a model before the full
tagging run. It writes a CSV (with the passage text) so a person can judge which
model's themes they agree with, and prints how often the two models agree.

Configure both providers in backend/.env (OP_API_KEY/OP_MODEL for OpenRouter,
OLLAMA_API_KEY/OLLAMA_MODEL for Ollama).

Usage:
    python -m scripts.theme_compare                         # 20 chunks, openrouter vs ollama
    python -m scripts.theme_compare --n 30 --a ollama --b openrouter --out cmp.csv
"""

import argparse
import csv
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import themes  # noqa: E402

COLUMNS = ["micro_session_id", "book", "text", "a_themes", "b_themes", "a_status", "b_status"]


def _tags(ask, text: str, min_score: int) -> tuple[str, list[tuple[str, int]]]:
    try:
        pairs = themes.parse_reply(ask(text))
    except (themes.ThemeReplyError, themes.ThemeProviderError, httpx.HTTPError):
        return "failed", []
    shown = sorted((p for p in pairs if p[1] >= min_score), key=lambda p: -p[1])
    return "done", shown


def compare(chunks: list[dict], ask_a, ask_b, *, min_score: int = themes.MIN_SHOWN_SCORE, delay: float = 0.0):
    """chunks: dicts with micro_session_id, book, text. ask_a/ask_b: text -> raw
    model reply. Returns (rows, summary)."""
    rows, matches, overlaps = [], [], []
    a_failed = b_failed = 0
    for n, chunk in enumerate(chunks):
        a_status, a_shown = _tags(ask_a, chunk["text"], min_score)
        b_status, b_shown = _tags(ask_b, chunk["text"], min_score)
        a_failed += a_status == "failed"
        b_failed += b_status == "failed"
        rows.append(
            {
                "micro_session_id": chunk["micro_session_id"],
                "book": chunk["book"],
                "text": chunk["text"],
                "a_themes": ";".join(t for t, _ in a_shown),
                "b_themes": ";".join(t for t, _ in b_shown),
                "a_status": a_status,
                "b_status": b_status,
            }
        )
        if a_status == "done" and b_status == "done":
            a_set, b_set = {t for t, _ in a_shown}, {t for t, _ in b_shown}
            top_a = a_shown[0][0] if a_shown else None
            top_b = b_shown[0][0] if b_shown else None
            matches.append(top_a is not None and top_a == top_b)
            overlaps.append(1.0 if not (a_set | b_set) else len(a_set & b_set) / len(a_set | b_set))
        if delay and n < len(chunks) - 1:
            time.sleep(delay)
    summary = {
        "n": len(chunks),
        "a_failed": a_failed,
        "b_failed": b_failed,
        "compared": len(matches),
        "top_theme_match": sum(matches) / len(matches) if matches else None,
        "mean_overlap": sum(overlaps) / len(overlaps) if overlaps else None,
    }
    return rows, summary


def write_csv(rows: list[dict], path) -> None:
    # utf-8-sig so Excel shows curly quotes correctly
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None) -> dict:
    from app.database import SessionLocal
    from scripts import theme_sample

    parser = argparse.ArgumentParser(description="Compare two models' theme tags on the same chunks.")
    parser.add_argument("--n", type=int, default=20, help="chunks to sample")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--a", default="openrouter", choices=["openrouter", "ollama"])
    parser.add_argument("--b", default="ollama", choices=["openrouter", "ollama"])
    parser.add_argument("--delay", type=float, default=2.0, help="seconds between chunks")
    parser.add_argument("--out", default="theme_compare.csv")
    args = parser.parse_args(argv)

    cfg_a, cfg_b = themes.current_config(args.a), themes.current_config(args.b)
    try:
        client_a, client_b = themes.make_client(cfg_a), themes.make_client(cfg_b)
    except themes.ThemeProviderError as err:
        print(f"{err}. Set it in backend/.env and re-run.", file=sys.stderr)
        return {"error": str(err)}

    db = SessionLocal()
    try:
        chunks = theme_sample.sample_chunks(db, n=args.n, seed=args.seed)
    finally:
        db.close()

    print(f"A = {cfg_a.provider}:{cfg_a.model} | B = {cfg_b.provider}:{cfg_b.model} | {len(chunks)} chunks", flush=True)
    try:
        rows, summary = compare(
            chunks,
            lambda t: themes.call_model(client_a, t, cfg_a),
            lambda t: themes.call_model(client_b, t, cfg_b),
            delay=args.delay,
        )
    finally:
        client_a.close()
        client_b.close()
    write_csv(rows, args.out)
    fmt = lambda v: "n/a" if v is None else f"{v:.2f}"  # noqa: E731
    print(f"compared {summary['compared']} (A failed {summary['a_failed']}, B failed {summary['b_failed']})")
    print(f"same top theme: {fmt(summary['top_theme_match'])} | mean theme overlap: {fmt(summary['mean_overlap'])}")
    print(f"Review the passages and both models' themes in {args.out}")
    return summary


if __name__ == "__main__":
    result = main()
    sys.exit(1 if "error" in result else 0)
