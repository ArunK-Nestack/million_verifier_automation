from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from app.clients.millionverifier import MillionVerifierClient
from app.config import settings
from app.exceptions import MillionVerifierAPIError
from app.models import VerificationJob


class VerificationService:
    def __init__(self, client: MillionVerifierClient | None = None) -> None:
        self.client = client or MillionVerifierClient()
        self.poll_interval = settings.poll_interval_seconds

    def verify_file(
        self,
        clean_csv_path: Path,
        download_dir: Path,
        on_progress: Callable[[VerificationJob], None] | None = None,
    ) -> tuple[VerificationJob, Path]:
        """
        Uploads a prepared CSV file to MillionVerifier, polls until finished,
        and downloads the full results CSV.
        """
        # Step 1: Upload
        initial_job = self.client.upload_csv(clean_csv_path)
        file_id = initial_job.file_id

        if not file_id:
            raise MillionVerifierAPIError("MillionVerifier did not return a valid file_id.")

        if on_progress:
            on_progress(initial_job)

        # Step 2: Poll status
        job = initial_job
        while job.status not in ("finished", "error"):
            time.sleep(self.poll_interval)
            job = self.client.get_file_info(file_id)
            if on_progress:
                on_progress(job)

        if job.status == "error":
            raise MillionVerifierAPIError(
                f"MillionVerifier job {file_id} failed: {job.error or 'Unknown error'}"
            )

        # Step 3: Download complete results
        download_dir.mkdir(parents=True, exist_ok=True)
        destination = download_dir / f"verified_{clean_csv_path.stem}.csv"
        downloaded_path = self.client.download_results(
            file_id=file_id,
            destination=destination,
            result_filter="all",
        )

        return job, downloaded_path
