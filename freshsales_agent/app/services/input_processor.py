from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


def _detect_dialect(path: Path) -> type[csv.Dialect]:
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        sample = handle.read(8192)
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        return csv.excel


def normalize_email(value: str | None) -> str:
    if value is None:
        return ""
    return value.strip().lower()


def generate_run_tag(file_stem: str) -> str:
    """
    Generates clean tag: apollo-YYYY-MM-DD-<cleaned_file_stem>
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    # Clean special characters from stem
    clean_stem = re.sub(r"[^\w\-]", "_", file_stem)
    clean_stem = re.sub(r"_+", "_", clean_stem).strip("_")
    return f"apollo-{date_str}-{clean_stem}"


@dataclass
class ParsedFile:
    source_path: Path
    file_stem: str
    tag_applied: str
    apollo_login_owner: str | None
    total_raw_rows: int
    duplicates_dropped: int
    unique_records: list[dict[str, str]]
    email_column: str


def parse_and_dedupe_file(file_path: Path) -> ParsedFile:
    """
    Reads a CSV file, detects email column, extracts Contact Owner,
    deduplicates emails within the file, and returns clean records.
    """
    if not file_path.is_file():
        raise FileNotFoundError(f"Input file not found: {file_path}")

    dialect = _detect_dialect(file_path)

    with file_path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, dialect=dialect)
        if not reader.fieldnames:
            raise ValueError(f"No headers found in CSV: {file_path}")

        raw_rows = list(reader)

    total_raw_rows = len(raw_rows)

    # Detect email column
    fieldnames = [str(f).strip() for f in (reader.fieldnames or []) if f is not None]
    email_col: str | None = None
    for f in fieldnames:
        if f.strip().lower() in ("email", "contact: emails", "email address", "contact: emails (primary)"):
            email_col = f
            break

    if not email_col:
        # Fallback to first column containing '@' in sample
        for f in fieldnames:
            if any("@" in str(r.get(f, "")) for r in raw_rows[:20]):
                email_col = f
                break

    if not email_col:
        raise ValueError(f"Could not find an email column in file: {file_path.name}")

    # Extract Apollo Login Owner from Contact Owner column
    apollo_owner: str | None = None
    for row in raw_rows:
        for k, v in row.items():
            if k and str(k).strip().lower() in ("contact owner", "contact: apollo login owner", "apollo login owner"):
                if v and str(v).strip():
                    apollo_owner = str(v).strip()
                    break
        if apollo_owner:
            break

    # Deduplicate within file
    seen_emails: set[str] = set()
    unique_records: list[dict[str, str]] = []
    duplicates_dropped = 0

    for row in raw_rows:
        clean_row = {
            (str(k).strip() if k is not None else ""): (str(v) if v is not None else "")
            for k, v in row.items()
        }
        em = normalize_email(clean_row.get(email_col))
        if not em:
            continue

        if em in seen_emails:
            duplicates_dropped += 1
            continue

        seen_emails.add(em)
        clean_row[email_col] = em
        unique_records.append(clean_row)

    tag = generate_run_tag(file_path.stem)

    return ParsedFile(
        source_path=file_path,
        file_stem=file_path.stem,
        tag_applied=tag,
        apollo_login_owner=apollo_owner,
        total_raw_rows=total_raw_rows,
        duplicates_dropped=duplicates_dropped,
        unique_records=unique_records,
        email_column=email_col,
    )
