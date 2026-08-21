from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path


EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)

COMMON_EMAIL_HEADERS = {
    "email",
    "email address",
    "email_address",
    "emailaddress",
    "work email",
    "work_email",
    "business email",
    "business_email",
    "primary email",
    "primary_email",
    "contact email",
    "contact_email",
}


@dataclass(frozen=True)
class PreparationResult:
    input_file: Path
    output_file: Path
    email_column: str
    total_rows: int
    blank_emails: int
    malformed_emails: int
    duplicate_emails: int
    unique_emails: int


def normalize_email(value: str | None) -> str:
    if value is None:
        return ""

    return value.strip().lower()


def is_valid_email(value: str) -> bool:
    if not value:
        return False

    return EMAIL_PATTERN.fullmatch(value) is not None


def _detect_dialect(path: Path) -> type[csv.Dialect]:
    with path.open(
        "r",
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as handle:
        sample = handle.read(8192)

    try:
        return csv.Sniffer().sniff(
            sample,
            delimiters=",;\t|",
        )
    except csv.Error:
        return csv.excel


def _read_rows(
    path: Path,
) -> tuple[list[str], list[dict[str, str]]]:
    dialect = _detect_dialect(path)

    with path.open(
        "r",
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as handle:
        reader = csv.DictReader(
            handle,
            dialect=dialect,
        )

        if not reader.fieldnames:
            raise ValueError(
                f"No header row found in CSV file: {path}"
            )

        headers = [
            str(header).strip()
            for header in reader.fieldnames
            if header is not None
        ]

        rows: list[dict[str, str]] = []

        for raw_row in reader:
            clean_row: dict[str, str] = {}

            for key, value in raw_row.items():
                if key is None:
                    continue

                clean_key = str(key).strip()

                if value is None:
                    clean_value = ""
                else:
                    clean_value = str(value)

                clean_row[clean_key] = clean_value

            rows.append(clean_row)

    return headers, rows


def detect_email_column(
    headers: list[str],
    rows: list[dict[str, str]],
) -> str:
    if not headers:
        raise ValueError("CSV contains no columns.")

    # First preference:
    # detect common email column names.
    for header in headers:
        normalized_header = (
            header.strip()
            .lower()
            .replace("-", " ")
        )

        if normalized_header in COMMON_EMAIL_HEADERS:
            return header

    # Second preference:
    # inspect actual values in each column.
    sample_rows = rows[:200]

    best_column: str | None = None
    best_score = 0.0

    for header in headers:
        non_blank = 0
        valid_emails = 0

        for row in sample_rows:
            value = normalize_email(
                row.get(header)
            )

            if not value:
                continue

            non_blank += 1

            if is_valid_email(value):
                valid_emails += 1

        if non_blank == 0:
            continue

        score = valid_emails / non_blank

        if score > best_score:
            best_score = score
            best_column = header

    if best_column is None or best_score < 0.50:
        raise ValueError(
            "Could not confidently detect an email column."
        )

    return best_column


def prepare_csv(
    input_file: str | Path,
    output_directory: str | Path = "prepared",
) -> PreparationResult:
    input_path = Path(input_file)

    if not input_path.is_file():
        raise FileNotFoundError(
            f"Input file not found: {input_path}"
        )

    if input_path.suffix.lower() != ".csv":
        raise ValueError(
            "Step 2A currently supports CSV files only."
        )

    headers, rows = _read_rows(input_path)

    email_column = detect_email_column(
        headers=headers,
        rows=rows,
    )

    total_rows = len(rows)
    blank_emails = 0
    malformed_emails = 0
    duplicate_emails = 0

    unique_emails: list[str] = []
    seen_emails: set[str] = set()

    for row in rows:
        email = normalize_email(
            row.get(email_column)
        )

        if not email:
            blank_emails += 1
            continue

        if not is_valid_email(email):
            malformed_emails += 1
            continue

        if email in seen_emails:
            duplicate_emails += 1
            continue

        seen_emails.add(email)
        unique_emails.append(email)

    output_dir = Path(output_directory)

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        output_dir
        / f"{input_path.stem}_verification_input.csv"
    )

    with output_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.writer(handle)

        writer.writerow(["email"])

        for email in unique_emails:
            writer.writerow([email])

    return PreparationResult(
        input_file=input_path,
        output_file=output_path,
        email_column=email_column,
        total_rows=total_rows,
        blank_emails=blank_emails,
        malformed_emails=malformed_emails,
        duplicate_emails=duplicate_emails,
        unique_emails=len(unique_emails),
    )