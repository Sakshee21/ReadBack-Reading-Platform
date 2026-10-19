"""Compare two human coders' theme labels with each other and with the LLM's.

Without this check the tags are just a model's opinion. Reports, per theme,
Cohen's kappa (present/absent) between the coders and between the LLM and each
coder, plus how often the LLM's top theme is among a coder's themes.

Usage:
    python -m scripts.theme_agreement coder1.csv coder2.csv --out agreement.json
"""

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import themes  # noqa: E402


def read_labels(path) -> dict[int, set[str]]:
    labels: dict[int, set[str]] = {}
    with open(path, newline="", encoding="utf-8-sig") as handle:  # Excel adds a BOM
        for row in csv.DictReader(handle):
            chosen = {row.get(f"theme_{i}", "").strip() for i in (1, 2, 3)} - {""}
            unknown = chosen - set(themes.THEMES)
            if unknown:
                raise ValueError(f"{path}: unknown theme(s) {sorted(unknown)} for chunk {row['micro_session_id']}")
            chunk_id = int(row["micro_session_id"])
            if chunk_id in labels:
                raise ValueError(f"{path}: chunk {chunk_id} appears more than once")
            labels[chunk_id] = chosen
    return labels


def cohen_kappa(a: list[bool], b: list[bool]) -> float | None:
    """Kappa for two present/absent label lists. None when it is undefined: no
    data, or chance agreement is already 1 (e.g. neither rater ever used the
    theme), where there is nothing to measure."""
    n = len(a)
    if n == 0:
        return None
    observed = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    expected = pa * pb + (1 - pa) * (1 - pb)
    if expected == 1:
        return None
    return (observed - expected) / (1 - expected)


def _pair_stats(x: dict[int, set[str]], y: dict[int, set[str]], ids: list[int]) -> dict:
    per_theme = {t: cohen_kappa([t in x[i] for i in ids], [t in y[i] for i in ids]) for t in themes.THEMES}
    defined = [k for k in per_theme.values() if k is not None]
    return {
        "per_theme_kappa": per_theme,
        "coded_counts": {t: [sum(t in x[i] for i in ids), sum(t in y[i] for i in ids)] for t in themes.THEMES},
        "mean_kappa": sum(defined) / len(defined) if defined else None,
        "exact_match": sum(x[i] == y[i] for i in ids) / len(ids) if ids else 0.0,
    }


def agreement_report(coder1, coder2, llm_rows, *, min_score: int = themes.MIN_SHOWN_SCORE, model: str = "") -> dict:
    """coder1/coder2: {chunk id: {themes}}; llm_rows: {chunk id: [(theme, score)]}
    for chunks the LLM actually tagged. Chunks it has not tagged are left out
    (and counted), never scored as "no theme"."""
    both = set(coder1) & set(coder2)
    ids = sorted(both & set(llm_rows))
    llm = {i: {t for t, s in llm_rows[i] if s >= min_score} for i in ids}
    top_hits = {"coder1": [], "coder2": []}
    for i in ids:
        ranked = sorted((r for r in llm_rows[i] if r[1] >= min_score), key=lambda r: -r[1])
        if not ranked:
            continue
        for name, coder in (("coder1", coder1), ("coder2", coder2)):
            top_hits[name].append(ranked[0][0] in coder[i])
    return {
        "n": len(ids),
        "excluded_without_llm_result": len(both - set(llm_rows)),
        "model": model or "",
        "prompt_version": themes.PROMPT_VERSION,
        "theme_list_version": themes.THEME_LIST_VERSION,
        "human_vs_human": _pair_stats(coder1, coder2, ids),
        "llm_vs_coder1": _pair_stats(llm, coder1, ids),
        "llm_vs_coder2": _pair_stats(llm, coder2, ids),
        "top_theme_in_coder": {k: (sum(v) / len(v) if v else None) for k, v in top_hits.items()},
    }


def _load_llm_rows(ids) -> tuple[dict, str]:
    from app.database import SessionLocal
    from app.models import MicroSessionTagging, MicroSessionTheme

    db = SessionLocal()
    try:
        done = {
            r[0]
            for r in db.query(MicroSessionTagging.micro_session_id).filter(
                MicroSessionTagging.micro_session_id.in_(list(ids)),
                MicroSessionTagging.status == "done",
            )
        }
        rows: dict[int, list] = {i: [] for i in done}
        model = ""
        for r in db.query(MicroSessionTheme).filter(
            MicroSessionTheme.micro_session_id.in_(list(ids)), MicroSessionTheme.source == "llm"
        ):
            if r.micro_session_id in rows:
                rows[r.micro_session_id].append((r.theme, r.score))
            model = r.model or model
        return rows, model
    finally:
        db.close()


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Agreement between two coders and the LLM.")
    parser.add_argument("coder1")
    parser.add_argument("coder2")
    parser.add_argument("--out", default="theme_agreement.json")
    args = parser.parse_args(argv)
    c1, c2 = read_labels(args.coder1), read_labels(args.coder2)
    llm_rows, model = _load_llm_rows(sorted(set(c1) & set(c2)))
    report = agreement_report(c1, c2, llm_rows, model=model)
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf8")
    hh, l1, l2 = report["human_vs_human"], report["llm_vs_coder1"], report["llm_vs_coder2"]
    fmt = lambda v: "n/a" if v is None else f"{v:.2f}"  # noqa: E731
    print(f"{report['n']} chunks compared ({report['excluded_without_llm_result']} left out: no LLM result yet)")
    print(f"model {model} | prompt v{report['prompt_version']}")
    print(f"mean kappa  coder1-coder2 {fmt(hh['mean_kappa'])} | llm-coder1 {fmt(l1['mean_kappa'])} | llm-coder2 {fmt(l2['mean_kappa'])}")
    print(f"LLM top theme is among the coder's themes: {report['top_theme_in_coder']}")
    print(f"Full per-theme report saved to {args.out}")


if __name__ == "__main__":
    main()
