from pathlib import Path
from typing import Any

import requests

from app.config import settings
from app.exceptions import MillionVerifierAPIError, MillionVerifierTransportError
from app.models import VerificationJob


class MillionVerifierClient:
    def __init__(self) -> None:
        settings.require_api_key()
        self.base_url = settings.bulk_base_url
        self.api_key = settings.api_key
        self.timeout = settings.http_timeout_seconds
        self.session = requests.Session()

    def _params(self, **extra: Any) -> dict[str, Any]:
        return {"key": self.api_key, **extra}

    def _json_response(self, response: requests.Response) -> dict[str, Any]:
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            raise MillionVerifierTransportError(
                f"MillionVerifier HTTP error: {exc}"
            ) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise MillionVerifierAPIError(
                "MillionVerifier returned a non-JSON response where JSON was expected."
            ) from exc

        if isinstance(data, dict) and data.get("error"):
            raise MillionVerifierAPIError(
                f"MillionVerifier API error: {data['error']}"
            )
        return data

    def upload_csv(self, csv_path: str | Path) -> VerificationJob:
        path = Path(csv_path)
        if not path.is_file():
            raise FileNotFoundError(path)

        if path.suffix.lower() != ".csv":
            raise ValueError(
                "Normalize XLS/XLSX to CSV before calling upload_csv()."
            )

        url = f"{self.base_url}/bulkapi/v2/upload"

        try:
            with path.open("rb") as handle:
                response = self.session.post(
                    url,
                    params=self._params(),
                    files={"file_contents": (path.name, handle, "text/csv")},
                    timeout=self.timeout,
                )
        except requests.RequestException as exc:
            raise MillionVerifierTransportError(
                f"Could not upload file to MillionVerifier: {exc}"
            ) from exc

        return VerificationJob.from_api(self._json_response(response))

    def get_file_info(self, file_id: str | int) -> VerificationJob:
        url = f"{self.base_url}/bulkapi/v2/fileinfo"

        try:
            response = self.session.get(
                url,
                params=self._params(file_id=file_id),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise MillionVerifierTransportError(
                f"Could not retrieve verification status: {exc}"
            ) from exc

        return VerificationJob.from_api(self._json_response(response))

    def download_results(
        self,
        file_id: str | int,
        destination: str | Path,
        result_filter: str = "all",
    ) -> Path:
        url = f"{self.base_url}/bulkapi/v2/download"
        destination_path = Path(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            response = self.session.get(
                url,
                params=self._params(file_id=file_id, filter=result_filter),
                timeout=self.timeout,
                stream=True,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise MillionVerifierTransportError(
                f"Could not download verification result: {exc}"
            ) from exc

        content_type = response.headers.get("content-type", "").lower()

        if "application/json" in content_type:
            try:
                payload = response.json()
            except ValueError as exc:
                raise MillionVerifierAPIError(
                    "MillionVerifier returned invalid JSON during download."
                ) from exc

            if payload.get("error"):
                raise MillionVerifierAPIError(
                    f"MillionVerifier API error: {payload['error']}"
                )

        with destination_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 128):
                if chunk:
                    handle.write(chunk)

        return destination_path

    def close(self) -> None:
        self.session.close()
