from __future__ import annotations

import time
from typing import Any
import requests

from app.config import settings
from app.exceptions import FreshsalesAPIError, FreshsalesTransportError


class FreshsalesClient:
    def __init__(self, api_key: str | None = None, domain: str | None = None):
        self.api_key = api_key or settings.api_key
        self.base_url = (domain or settings.base_url).rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Token token={self.api_key}",
            "Content-Type": "application/json",
        })

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = self.session.request(method, url, timeout=60, **kwargs)
            if response.status_code == 404:
                return {}
            response.raise_for_status()
            if response.content:
                return response.json()
            return {}
        except requests.HTTPError as exc:
            raise FreshsalesAPIError(f"Freshsales HTTP {response.status_code}: {response.text}") from exc
        except requests.RequestException as exc:
            raise FreshsalesTransportError(f"Freshsales connection error: {exc}") from exc

    def lookup_contact_by_email(self, email: str) -> dict[str, Any] | None:
        """
        Looks up a single contact by email in Freshsales.
        """
        path = "api/contacts/lookup"
        data = self._request("GET", path, params={"q": email, "entities": "contact"})
        contacts = data.get("contacts", {}).get("contacts", [])
        if contacts:
            return contacts[0]
        return None

    def batch_lookup_emails(self, emails: list[str]) -> dict[str, dict[str, Any]]:
        """
        Looks up a list of emails in Freshsales, returning {email: contact_data}.
        """
        found_map: dict[str, dict[str, Any]] = {}
        for email in emails:
            res = self.lookup_contact_by_email(email)
            if res:
                found_map[email.lower().strip()] = res
        return found_map

    def bulk_upsert_contacts(self, contacts: list[dict[str, Any]]) -> str:
        """
        Submits a batch of contacts to Freshsales Bulk Upsert API.
        Returns job_id.
        """
        path = "api/contacts/bulk_upsert"
        payload = {"contacts": contacts}
        res = self._request("POST", path, json=payload)
        job_id = res.get("job_id") or res.get("id") or str(res.get("job", {}).get("id", ""))
        return str(job_id)

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        """
        Polls status of a bulk job.
        """
        path = f"api/jobs/{job_id}"
        return self._request("GET", path)

    def create_or_update_contact_single(self, email: str, payload: dict[str, Any], existing_id: int | str | None = None) -> dict[str, Any]:
        """
        Direct single contact fallback upsert.
        """
        if existing_id:
            path = f"api/contacts/{existing_id}"
            return self._request("PUT", path, json={"contact": payload})
        else:
            path = "api/contacts"
            payload["emails"] = email
            return self._request("POST", path, json={"contact": payload})

    def close(self) -> None:
        self.session.close()
