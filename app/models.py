from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class VerificationJob:
    file_id: str
    file_name: str | None
    status: str
    percent: int | float
    total_rows: int
    unique_emails: int
    verified: int
    unverified: int
    ok: int
    catch_all: int
    disposable: int
    invalid: int
    unknown: int
    estimated_time_sec: int
    error: str

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "VerificationJob":
        return cls(
            file_id=str(data.get("file_id", "")),
            file_name=data.get("file_name"),
            status=str(data.get("status", "")),
            percent=data.get("percent", 0),
            total_rows=int(data.get("total_rows", 0) or 0),
            unique_emails=int(data.get("unique_emails", 0) or 0),
            verified=int(data.get("verified", 0) or 0),
            unverified=int(data.get("unverified", 0) or 0),
            ok=int(data.get("ok", 0) or 0),
            catch_all=int(data.get("catch_all", 0) or 0),
            disposable=int(data.get("disposable", 0) or 0),
            invalid=int(data.get("invalid", 0) or 0),
            unknown=int(data.get("unknown", 0) or 0),
            estimated_time_sec=int(data.get("estimated_time_sec", 0) or 0),
            error=str(data.get("error", "") or ""),
        )


@dataclass(frozen=True)
class CategorizationSummary:
    good_count: int
    bad_count: int
    risky_count: int
    good_file: Path
    bad_file: Path
    risky_file: Path


@dataclass
class FileProcessResult:
    input_file: Path
    output_dir: Path
    status: str  # "completed", "failed", "skipped"
    total_input_rows: int = 0
    unique_emails: int = 0
    blank_emails: int = 0
    malformed_emails: int = 0
    duplicate_emails: int = 0
    good_count: int = 0
    bad_count: int = 0
    risky_count: int = 0
    job_id: str | None = None
    error_message: str | None = None
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_file": str(self.input_file),
            "output_dir": str(self.output_dir),
            "status": self.status,
            "total_input_rows": self.total_input_rows,
            "unique_emails": self.unique_emails,
            "blank_emails": self.blank_emails,
            "malformed_emails": self.malformed_emails,
            "duplicate_emails": self.duplicate_emails,
            "good_count": self.good_count,
            "bad_count": self.bad_count,
            "risky_count": self.risky_count,
            "job_id": self.job_id,
            "error_message": self.error_message,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }
