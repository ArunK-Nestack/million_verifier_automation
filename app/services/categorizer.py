from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from app.models import CategorizationSummary


def _detect_dialect(path: Path) -> type[csv.Dialect]:
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        sample = handle.read(8192)

    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        return csv.excel


def classify_row(row: dict[str, str]) -> str:
    """
    Classifies a MillionVerifier output row into 'good', 'bad', or 'risky'.
    """
    # Normalize row keys to lowercase for robust matching
    normalized_row = {
        str(k).strip().lower(): str(v).strip().lower()
        for k, v in row.items()
        if k is not None
    }

    # 1. Check 'quality' field (MillionVerifier standard: good, bad, risky)
    quality = normalized_row.get("quality", "")
    if quality in ("good", "valid"):
        return "good"
    if quality in ("bad", "invalid"):
        return "bad"
    if quality in ("risky", "unknown", "catch_all", "catchall"):
        return "risky"

    # 2. Check 'result' or 'status' field
    result = normalized_row.get("result", "") or normalized_row.get("status", "")
    if result in ("ok", "good", "valid"):
        return "good"
    if result in ("invalid", "disposable", "bad", "spam_trap", "error"):
        return "bad"
    if result in ("catch_all", "catchall", "unknown", "recheck", "risky"):
        return "risky"

    # 3. Check 'subresult' if result wasn't explicit
    subresult = normalized_row.get("subresult", "")
    if "syntax" in subresult or "disposable" in subresult or "invalid" in subresult:
        return "bad"
    if "catch_all" in subresult or "timeout" in subresult or "greylist" in subresult:
        return "risky"

    # Default fallback
    return "risky"


def categorize_results(
    csv_path: Path,
    output_subfolder: Path,
    base_filename: str,
) -> CategorizationSummary:
    """
    Reads the downloaded verification CSV, splits it into Good, Bad, and Risky datasets,
    and writes them into dedicated subfolders under output_subfolder.
    """
    if not csv_path.is_file():
        raise FileNotFoundError(f"Verification results file not found: {csv_path}")

    dialect = _detect_dialect(csv_path)

    good_rows: list[dict[str, str]] = []
    bad_rows: list[dict[str, str]] = []
    risky_rows: list[dict[str, str]] = []
    fieldnames: list[str] = []

    with csv_path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, dialect=dialect)
        if reader.fieldnames:
            fieldnames = [str(f).strip() for f in reader.fieldnames if f is not None]

        for row in reader:
            clean_row = {
                (str(k).strip() if k is not None else ""): (str(v) if v is not None else "")
                for k, v in row.items()
            }
            category = classify_row(clean_row)
            if category == "good":
                good_rows.append(clean_row)
            elif category == "bad":
                bad_rows.append(clean_row)
            else:
                risky_rows.append(clean_row)

    if not fieldnames:
        fieldnames = ["email", "quality", "result"]

    # Create subdirectories
    good_dir = output_subfolder / "good"
    bad_dir = output_subfolder / "bad"
    risky_dir = output_subfolder / "risky"

    good_dir.mkdir(parents=True, exist_ok=True)
    bad_dir.mkdir(parents=True, exist_ok=True)
    risky_dir.mkdir(parents=True, exist_ok=True)

    good_file = good_dir / f"{base_filename}_good.csv"
    bad_file = bad_dir / f"{base_filename}_bad.csv"
    risky_file = risky_dir / f"{base_filename}_risky.csv"

    def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for r in rows:
                writer.writerow(r)

    _write_csv(good_file, good_rows)
    _write_csv(bad_file, bad_rows)
    _write_csv(risky_file, risky_rows)

    return CategorizationSummary(
        good_count=len(good_rows),
        bad_count=len(bad_rows),
        risky_count=len(risky_rows),
        good_file=good_file,
        bad_file=bad_file,
        risky_file=risky_file,
    )
