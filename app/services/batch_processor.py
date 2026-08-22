from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import settings
from app.models import FileProcessResult, VerificationJob
from app.services.categorizer import categorize_results
from app.services.input_processor import prepare_csv
from app.services.verifier import VerificationService


class BatchProcessor:
    def __init__(
        self,
        verifier_service: VerificationService | None = None,
        prepared_cache_dir: Path | str = "prepared",
        results_cache_dir: Path | str = "results",
        delete_input_file: bool | None = None,
    ) -> None:
        self.verifier = verifier_service or VerificationService()
        self.prepared_cache_dir = Path(prepared_cache_dir)
        self.results_cache_dir = Path(results_cache_dir)
        self.delete_input_file = (
            delete_input_file if delete_input_file is not None else settings.delete_input_file
        )

    def find_input_files(self, input_dir: Path) -> list[Path]:
        if not input_dir.exists() or not input_dir.is_dir():
            raise FileNotFoundError(f"Input directory does not exist: {input_dir}")

        supported_extensions = {".csv"}
        files = [
            p
            for p in sorted(input_dir.iterdir(), key=lambda f: f.stat().st_mtime if f.is_file() else 0)
            if p.is_file()
            and p.suffix.lower() in supported_extensions
            and not p.name.startswith((".", "~"))
        ]
        return files

    def process_file(
        self,
        input_file: Path,
        output_dir: Path,
    ) -> FileProcessResult:
        file_stem = input_file.stem

        result = FileProcessResult(
            input_file=input_file,
            output_dir=output_dir,
            status="in_progress",
        )

        try:
            print(f"\n[{input_file.name}] Step 1/4: Cleaning & normalizing...")
            prep_result = prepare_csv(
                input_file=input_file,
                output_directory=self.prepared_cache_dir,
            )

            result.total_input_rows = prep_result.total_rows
            result.unique_emails = prep_result.unique_emails
            result.blank_emails = prep_result.blank_emails
            result.malformed_emails = prep_result.malformed_emails
            result.duplicate_emails = prep_result.duplicate_emails

            print(
                f"[{input_file.name}] Cleaned {prep_result.total_rows} rows -> "
                f"{prep_result.unique_emails} unique valid emails "
                f"(duplicates: {prep_result.duplicate_emails}, "
                f"malformed: {prep_result.malformed_emails}, "
                f"blank: {prep_result.blank_emails})."
            )

            if prep_result.unique_emails == 0:
                print(f"[{input_file.name}] Warning: No valid emails found to verify.")
                result.status = "skipped"
                result.error_message = "No valid emails found in file."
                result.completed_at = datetime.now().isoformat()
                self._save_summary(result, output_dir)
                self._cleanup_input_file(input_file)
                return result

            print(f"[{input_file.name}] Step 2/4: Uploading & verifying via MillionVerifier...")

            def progress_callback(job: VerificationJob) -> None:
                percent = job.percent
                verified = job.verified
                total = job.total_rows
                est = job.estimated_time_sec
                print(
                    f"  -> Job {job.file_id}: status={job.status}, "
                    f"progress={percent}% ({verified}/{total} verified), "
                    f"est. remaining={est}s",
                    flush=True,
                )

            job, downloaded_csv = self.verifier.verify_file(
                clean_csv_path=prep_result.output_file,
                download_dir=self.results_cache_dir,
                on_progress=progress_callback,
            )

            result.job_id = job.file_id

            print(f"[{input_file.name}] Step 3/4: Categorizing into Good, Bad, and Risky files...")
            cat_summary = categorize_results(
                csv_path=downloaded_csv,
                output_dir=output_dir,
                base_filename=file_stem,
                total_input_count=prep_result.total_rows,
            )

            result.good_count = cat_summary.good_count
            result.bad_count = cat_summary.bad_count
            result.risky_count = cat_summary.risky_count
            result.status = "completed"
            result.completed_at = datetime.now().isoformat()

            print(
                f"[{input_file.name}] Results categorized:\n"
                f"  Good emails:  {cat_summary.good_count} -> {cat_summary.good_file}\n"
                f"  Bad emails:   {cat_summary.bad_count} -> {cat_summary.bad_file}\n"
                f"  Risky emails: {cat_summary.risky_count} -> {cat_summary.risky_file}"
            )

            # Step 4: Delete/Clean up input file from input directory
            if self.delete_input_file:
                print(f"[{input_file.name}] Step 4/4: Deleting original file from input folder...")
                self._cleanup_input_file(input_file)

        except Exception as exc:
            print(f"[{input_file.name}] ERROR: {exc}")
            result.status = "failed"
            result.error_message = str(exc)
            result.completed_at = datetime.now().isoformat()

        self._save_summary(result, output_dir)
        return result

    def _cleanup_input_file(self, file_path: Path) -> None:
        try:
            if file_path.exists() and file_path.is_file():
                file_path.unlink()
                print(f"  -> Deleted from input folder: {file_path.name}")
        except Exception as exc:
            print(f"  -> Warning: Could not delete input file {file_path.name}: {exc}")

    def _save_summary(self, result: FileProcessResult, output_dir: Path) -> None:
        summaries_dir = output_dir / "summaries"
        summaries_dir.mkdir(parents=True, exist_ok=True)
        summary_file = summaries_dir / f"{result.input_file.stem}_run_summary.json"
        with summary_file.open("w", encoding="utf-8") as handle:
            json.dump(result.to_dict(), handle, indent=2)

    def run_batch_once(
        self,
        input_dir: Path,
        output_dir: Path,
    ) -> list[FileProcessResult]:
        output_dir.mkdir(parents=True, exist_ok=True)
        files = self.find_input_files(input_dir)

        print("=" * 70)
        print(" MillionVerifier Folder-to-Folder Batch (Single Run)")
        print("=" * 70)
        print(f"Input folder:  {input_dir}")
        print(f"Output folder: {output_dir}")
        print(f"Found {len(files)} file(s) to process.")
        print("=" * 70)

        if not files:
            print(f"No CSV files found in {input_dir}.")
            return []

        results: list[FileProcessResult] = []
        for index, file_path in enumerate(files, 1):
            print(f"\n>>> [{index}/{len(files)}] Processing: {file_path.name}")
            res = self.process_file(file_path, output_dir)
            results.append(res)

        return results

    def watch_and_process(
        self,
        input_dir: Path,
        output_dir: Path,
        watch_interval: int | None = None,
    ) -> None:
        """
        Continuously watches input_dir. Whenever a file appears, processes it,
        deletes it from input_dir, downloads and categorizes it into output_dir,
        and immediately proceeds to the next file.
        """
        interval = watch_interval or settings.watch_interval_seconds
        output_dir.mkdir(parents=True, exist_ok=True)

        print("=" * 70)
        print(" MillionVerifier Continuous Automation Agent Active")
        print("=" * 70)
        print(f"Watching Input:  {input_dir}")
        print(f"Writing Output:  {output_dir}")
        print(f"Poll Interval:   {settings.poll_interval_seconds}s (MillionVerifier check)")
        print(f"Watch Interval:  {interval}s (Input folder check when idle)")
        print(f"Auto-delete:     {'Enabled' if self.delete_input_file else 'Disabled'}")
        print("=" * 70)
        print("Waiting for files to arrive... (Press Ctrl+C to stop)")

        try:
            while True:
                files = self.find_input_files(input_dir)

                if files:
                    # Take the first file in the queue
                    current_file = files[0]
                    remaining = len(files) - 1
                    print(f"\n[Queue] Found file '{current_file.name}' ({remaining} more in queue). Starting processing...")

                    self.process_file(current_file, output_dir)

                    print(f"[Queue] Finished '{current_file.name}'. Checking for next file immediately...")
                    # Loop immediately without sleeping when files were processed
                    continue

                # No files found, sleep and check again
                time.sleep(interval)

        except KeyboardInterrupt:
            print("\n[Watcher] Automation agent stopped by user.")
