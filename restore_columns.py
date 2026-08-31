from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from app.config import settings
from app.services.categorizer import classify_row
from app.services.input_processor import _detect_dialect, detect_email_column, normalize_email


def find_verified_result_file(stem: str, results_dir: Path) -> Path | None:
    """
    Finds the cached verified result file corresponding to the original file stem.
    """
    candidates = [
        results_dir / f"verified_{stem}_verification_input.csv",
        results_dir / f"verified_{stem}.csv",
        results_dir / f"{stem}_verification_input.csv",
        results_dir / f"{stem}.csv",
    ]
    for c in candidates:
        if c.is_file():
            return c

    # Fallback: fuzzy match on stem within results_dir
    normalized_stem = stem.strip().lower()
    for p in results_dir.glob("*.csv"):
        if normalized_stem in p.name.lower():
            return p

    return None


def merge_and_categorize(
    original_csv: Path,
    verified_csv: Path,
    output_dir: Path,
) -> dict[str, int]:
    """
    Merges original input columns with verification results and writes out
    categorized CSVs (good, bad, risky) with all original columns intact.
    """
    # 1. Read original input rows
    orig_dialect = _detect_dialect(original_csv)
    with original_csv.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        orig_reader = csv.DictReader(handle, dialect=orig_dialect)
        if not orig_reader.fieldnames:
            raise ValueError(f"No header row found in original CSV: {original_csv}")

        orig_headers = [str(h).strip() for h in orig_reader.fieldnames if h is not None]
        orig_rows: list[dict[str, str]] = []
        for raw_row in orig_reader:
            clean_row = {
                (str(k).strip() if k is not None else ""): (str(v) if v is not None else "")
                for k, v in raw_row.items()
            }
            orig_rows.append(clean_row)

    email_col = detect_email_column(orig_headers, orig_rows)

    # Map normalized email -> original row (first occurrence)
    email_to_orig_row: dict[str, dict[str, str]] = {}
    for r in orig_rows:
        em = normalize_email(r.get(email_col))
        if em and em not in email_to_orig_row:
            email_to_orig_row[em] = r

    # 2. Read verified result rows
    ver_dialect = _detect_dialect(verified_csv)
    with verified_csv.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        ver_reader = csv.DictReader(handle, dialect=ver_dialect)
        if not ver_reader.fieldnames:
            raise ValueError(f"No header row found in verified CSV: {verified_csv}")

        ver_headers = [str(h).strip() for h in ver_reader.fieldnames if h is not None]
        ver_email_col = "email" if "email" in ver_headers else detect_email_column(ver_headers, [])

        ver_extra_headers = [h for h in ver_headers if h != ver_email_col and h not in orig_headers]
        final_headers = list(orig_headers) + ver_extra_headers

        good_rows: list[dict[str, str]] = []
        bad_rows: list[dict[str, str]] = []
        risky_rows: list[dict[str, str]] = []

        for row in ver_reader:
            clean_ver_row = {
                (str(k).strip() if k is not None else ""): (str(v) if v is not None else "")
                for k, v in row.items()
            }
            email = normalize_email(clean_ver_row.get(ver_email_col))
            if not email:
                continue

            # Merge original columns with verification fields
            orig_data = email_to_orig_row.get(email, {})
            merged_row = dict(orig_data)

            # If original data was missing or partial, ensure email is present
            if email_col not in merged_row:
                merged_row[email_col] = email

            # Add verification result columns (quality, result, subresult, etc.)
            for col in ver_extra_headers:
                merged_row[col] = clean_ver_row.get(col, "")

            # Keep verification status fields for classification
            category = classify_row(clean_ver_row)
            if category == "good":
                good_rows.append(merged_row)
            elif category == "bad":
                bad_rows.append(merged_row)
            else:
                risky_rows.append(merged_row)

    # 3. Write categorized outputs
    good_dir = output_dir / "good"
    bad_dir = output_dir / "bad"
    risky_dir = output_dir / "risky"

    good_dir.mkdir(parents=True, exist_ok=True)
    bad_dir.mkdir(parents=True, exist_ok=True)
    risky_dir.mkdir(parents=True, exist_ok=True)

    base_name = original_csv.stem
    total_input_count = len(orig_rows)
    good_count = len(good_rows)
    bad_count = len(bad_rows)
    risky_count = len(risky_rows)

    good_file = good_dir / f"{base_name} - good - {good_count} good - {total_input_count} total.csv"
    bad_file = bad_dir / f"{base_name} - bad.csv"
    risky_file = risky_dir / f"{base_name} - risky.csv"

    def _write(path: Path, rows: list[dict[str, str]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as h:
            writer = csv.DictWriter(h, fieldnames=final_headers, extrasaction="ignore")
            writer.writeheader()
            for r in rows:
                writer.writerow(r)

    _write(good_file, good_rows)
    _write(bad_file, bad_rows)
    _write(risky_file, risky_rows)

    # Save summary
    import json
    from datetime import datetime

    summaries_dir = output_dir / "summaries"
    summaries_dir.mkdir(parents=True, exist_ok=True)
    summary_data = {
        "input_file": str(original_csv),
        "output_dir": str(output_dir),
        "status": "restored",
        "total_input_rows": total_input_count,
        "unique_emails": len(email_to_orig_row),
        "good_count": good_count,
        "bad_count": bad_count,
        "risky_count": risky_count,
        "verified_source_file": str(verified_csv),
        "restored_at": datetime.now().isoformat(),
    }
    with (summaries_dir / f"{base_name}_run_summary.json").open("w", encoding="utf-8") as sf:
        json.dump(summary_data, sf, indent=2)

    return {
        "good": good_count,
        "bad": bad_count,
        "risky": risky_count,
        "total": good_count + bad_count + risky_count,
    }


def restore_all(
    input_dir: Path,
    output_dir: Path,
    results_dir: Path,
    delete_input: bool = False,
) -> None:
    if not input_dir.exists():
        print(f"Error: Input directory does not exist: {input_dir}")
        sys.exit(1)

    if not results_dir.exists():
        print(f"Error: Results directory does not exist: {results_dir}")
        sys.exit(1)

    csv_files = [p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() == ".csv"]

    if not csv_files:
        print(f"No CSV files found in input directory: {input_dir}")
        print("Please place your original CSV files into the input directory and run again.")
        return

    print("=" * 70)
    print(" MillionVerifier Offline Column Restore & Merge")
    print("=" * 70)
    print(f"Input Directory:   {input_dir}")
    print(f"Results Directory: {results_dir}")
    print(f"Output Directory:  {output_dir}")
    print(f"Auto-delete input: {'Enabled' if delete_input else 'Disabled'}")
    print(f"Found {len(csv_files)} file(s) to process.")
    print("=" * 70)

    success_count = 0
    missing_count = 0

    for i, orig_file in enumerate(csv_files, 1):
        print(f"\n[{i}/{len(csv_files)}] Processing: {orig_file.name}")
        verified_file = find_verified_result_file(orig_file.stem, results_dir)

        if not verified_file:
            print(f"  -> [SKIPPED] No matching cached verification result found in {results_dir}")
            missing_count += 1
            continue

        print(f"  -> Found cached result: {verified_file.name}")
        counts = merge_and_categorize(
            original_csv=orig_file,
            verified_csv=verified_file,
            output_dir=output_dir,
        )
        print(
            f"  -> Restored successfully with all original columns! "
            f"(Good: {counts['good']}, Bad: {counts['bad']}, Risky: {counts['risky']})"
        )

        if delete_input:
            try:
                orig_file.unlink()
                print(f"  -> Deleted source file from input folder: {orig_file.name}")
            except Exception as e:
                print(f"  -> Warning: Could not delete input file: {e}")

        success_count += 1

    print("\n" + "=" * 70)
    print(f"Restore Complete! Processed: {success_count}, Skipped (no cache): {missing_count}")
    print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge original CSV columns with cached MillionVerifier results without re-verifying."
    )
    parser.add_argument(
        "--input-dir",
        "-i",
        default=str(settings.default_input_dir),
        help=f"Folder containing original CSV files (default: {settings.default_input_dir})",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        default=str(settings.default_output_dir),
        help=f"Destination output folder (default: {settings.default_output_dir})",
    )
    parser.add_argument(
        "--results-dir",
        "-r",
        default="results",
        help="Folder containing cached verification results (default: results)",
    )
    parser.add_argument(
        "--delete-input",
        action="store_true",
        help="Delete source CSV from input folder after successful restore",
    )

    args = parser.parse_args()

    restore_all(
        input_dir=Path(args.input_dir),
        output_dir=Path(args.output_dir),
        results_dir=Path(args.results_dir),
        delete_input=args.delete_input,
    )


if __name__ == "__main__":
    main()
