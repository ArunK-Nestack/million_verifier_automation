from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app.clients.freshsales import FreshsalesClient
from app.config import settings
from app.database.db import init_db
from app.logger import logger
from app.models import FileProcessingResult
from app.services.field_mapper import map_row_to_contact_payload
from app.services.input_processor import parse_and_dedupe_file
from app.services.reporter import generate_audit_csv_report, save_run_metrics_to_db
from app.services.tld_filter import filter_by_tld
from app.services.upsert_engine import resolve_delta_update


class BatchProcessor:
    def __init__(
        self,
        client: FreshsalesClient | None = None,
        auto_delete_input: bool | None = None,
    ) -> None:
        init_db()
        self.client = client or FreshsalesClient()
        self.auto_delete_input = (
            auto_delete_input if auto_delete_input is not None else settings.auto_delete_input
        )

    def find_input_files(self, input_dir: Path) -> list[Path]:
        if not input_dir.exists() or not input_dir.is_dir():
            return []
        return [
            p
            for p in sorted(input_dir.iterdir(), key=lambda f: f.stat().st_mtime if f.is_file() else 0)
            if p.is_file() and p.suffix.lower() == ".csv" and not p.name.startswith((".", "~"))
        ]

    def process_file(
        self,
        file_path: Path,
        reports_dir: Path,
    ) -> FileProcessingResult:
        logger.info("=" * 70)
        logger.info(f"Processing File: {file_path.name}")
        logger.info("=" * 70)

        # 1. Parse & deduplicate file
        parsed = parse_and_dedupe_file(file_path)
        logger.info(
            f"Step 1/5: Parsed {parsed.total_raw_rows} raw rows -> "
            f"{len(parsed.unique_records)} unique contacts (Dropped {parsed.duplicates_dropped} duplicate emails)."
        )
        logger.info(f"  -> Apollo Login Owner: {parsed.apollo_login_owner or 'None'}")
        logger.info(f"  -> Run Tag Applied:    {parsed.tag_applied}")

        audit_rows: list[dict[str, Any]] = []

        # 2. Layer 1: 33 TLD Domain Filter
        valid_records, excluded_tld_records = filter_by_tld(
            parsed.unique_records,
            email_col=parsed.email_column,
        )
        tld_filtered_count = len(excluded_tld_records)
        logger.info(
            f"Step 2/5: 33-TLD Filter evaluated -> {len(valid_records)} allowed domains, "
            f"{tld_filtered_count} blocked domains excluded."
        )

        for exc_row in excluded_tld_records:
            audit_rows.append({
                "email": exc_row.get(parsed.email_column, ""),
                "action": "excluded_tld",
                "fields_filled_count": 0,
                "fields_filled_names": "",
                "error_reason": "Matched DELETE_TLDS blocklist",
            })

        result = FileProcessingResult(
            source_filename=file_path.name,
            tag_applied=parsed.tag_applied,
            apollo_login_owner=parsed.apollo_login_owner,
            total_input_rows=parsed.total_raw_rows,
            file_duplicates_skipped=parsed.duplicates_dropped,
            tld_filtered_count=tld_filtered_count,
            contacts_sent_to_crm=len(valid_records),
        )

        if not valid_records:
            logger.warning("No valid records left to process after TLD filter.")
            result.status = "completed"
            result.completed_at = datetime.now().isoformat()
            report_file = generate_audit_csv_report(file_path.name, audit_rows, reports_dir)
            result.report_file_path = str(report_file)
            save_run_metrics_to_db(result, audit_rows)
            if self.auto_delete_input:
                self._cleanup_input_file(file_path)
            return result

        # 3. CRM Lookup & Delta Resolution
        logger.info(f"Step 3/5: Batch looking up {len(valid_records)} emails in Freshsales CRM...")
        all_emails = [r.get(parsed.email_column, "").lower().strip() for r in valid_records if r.get(parsed.email_column)]

        # Lookup in chunks of 50
        existing_crm_map: dict[str, dict[str, Any]] = {}
        for i in range(0, len(all_emails), 50):
            chunk = all_emails[i : i + 50]
            found = self.client.batch_lookup_emails(chunk)
            existing_crm_map.update(found)

        logger.info(f"  -> Lookup complete: {len(existing_crm_map)} already exist in CRM, {len(valid_records) - len(existing_crm_map)} brand new.")

        # Build payloads
        upsert_payloads: list[dict[str, Any]] = []

        for row in valid_records:
            incoming = map_row_to_contact_payload(
                row=row,
                tag=parsed.tag_applied,
                default_owner_id=settings.default_owner_id,
            )
            email_lower = incoming.email.lower().strip()

            if email_lower in existing_crm_map:
                # Existing contact -> resolve delta without overwrite
                existing_record = existing_crm_map[email_lower]
                delta = resolve_delta_update(
                    incoming=incoming,
                    existing_crm_record=existing_record,
                    tag=parsed.tag_applied,
                )
                delta["emails"] = incoming.email
                upsert_payloads.append(delta)

                filled_keys = [k for k in delta if k not in ("emails", "tags")]
                audit_rows.append({
                    "email": incoming.email,
                    "action": "updated",
                    "fields_filled_count": len(filled_keys),
                    "fields_filled_names": ", ".join(filled_keys),
                    "error_reason": "",
                })
                result.updated_in_crm_count += 1
            else:
                # Brand new contact -> full payload
                full_data = incoming.to_freshsales_dict()
                upsert_payloads.append(full_data)

                audit_rows.append({
                    "email": incoming.email,
                    "action": "created",
                    "fields_filled_count": len(full_data),
                    "fields_filled_names": "All",
                    "error_reason": "",
                })
                result.freshly_created_count += 1

        # 4. Dispatch Bulk Upsert Jobs (Batches of 100)
        batch_size = settings.batch_size
        logger.info(f"Step 4/5: Dispatching {len(upsert_payloads)} records in batches of {batch_size} to Freshsales...")

        job_ids: list[str] = []
        for i in range(0, len(upsert_payloads), batch_size):
            batch_slice = upsert_payloads[i : i + batch_size]
            try:
                job_id = self.client.bulk_upsert_contacts(batch_slice)
                job_ids.append(job_id)
                logger.info(f"  -> Batch [{len(job_ids)}]: Dispatched job_id={job_id} ({len(batch_slice)} records)")
            except Exception as exc:
                logger.error(f"  -> Batch submission failed: {exc}")
                result.failed_errors_count += len(batch_slice)

        # 5. Poll Job Status
        logger.info(f"Step 5/5: Monitoring {len(job_ids)} bulk jobs until completion (Polling every {settings.poll_interval_seconds}s)...")
        pending_jobs = set(job_ids)
        while pending_jobs:
            time.sleep(settings.poll_interval_seconds)
            done_jobs: set[str] = set()

            for jid in pending_jobs:
                try:
                    status_data = self.client.get_job_status(jid)
                    status_str = str(status_data.get("status", "")).lower()
                    if status_str in ("completed", "finished", "success", "done"):
                        done_jobs.add(jid)
                        logger.info(f"  -> Job {jid}: COMPLETED")
                    elif status_str in ("failed", "error"):
                        done_jobs.add(jid)
                        logger.error(f"  -> Job {jid}: FAILED ({status_data.get('error', 'Unknown error')})")
                        result.failed_errors_count += batch_size
                except Exception:
                    pass

            pending_jobs -= done_jobs

        result.status = "completed"
        result.completed_at = datetime.now().isoformat()

        # Generate report and save to SQLite
        report_file = generate_audit_csv_report(file_path.name, audit_rows, reports_dir)
        result.report_file_path = str(report_file)
        run_id = save_run_metrics_to_db(result, audit_rows)

        logger.info("=" * 70)
        logger.info(" RUN SUMMARY (Saved to SQLite DB)")
        logger.info("=" * 70)
        logger.info(f"Run ID:                 #{run_id}")
        logger.info(f"Source File:            {result.source_filename}")
        logger.info(f"Apollo Owner:           {result.apollo_login_owner or 'N/A'}")
        logger.info(f"Run Tag:                {result.tag_applied}")
        logger.info(f"Raw Input Rows:         {result.total_input_rows}")
        logger.info(f"Duplicates Dropped:     {result.file_duplicates_skipped}")
        logger.info(f"TLD Filtered (33 cc):   {result.tld_filtered_count}")
        logger.info(f"Sent to Freshsales:     {result.contacts_sent_to_crm}")
        logger.info(f"  - Freshly Created:    {result.freshly_created_count}")
        logger.info(f"  - Existing & Updated: {result.updated_in_crm_count}")
        logger.info(f"  - Failed Errors:      {result.failed_errors_count}")
        logger.info(f"Overall Success Rate:   {result.overall_success_percentage}%")
        logger.info(f"Detailed Audit CSV:     {report_file}")
        logger.info("=" * 70)

        # 6. Auto-delete input file
        if self.auto_delete_input:
            self._cleanup_input_file(file_path)

        return result

    def _cleanup_input_file(self, file_path: Path) -> None:
        try:
            if file_path.exists() and file_path.is_file():
                file_path.unlink()
                logger.info(f"[Cleanup] Deleted source file from input queue: {file_path.name}")
        except Exception as exc:
            logger.warning(f"[Cleanup Warning] Could not delete {file_path.name}: {exc}")

    def watch_and_process(self, input_dir: Path, reports_dir: Path) -> None:
        """
        Continuously watches input_dir for new files and processes them one by one.
        """
        input_dir.mkdir(parents=True, exist_ok=True)
        reports_dir.mkdir(parents=True, exist_ok=True)

        logger.info("=" * 70)
        logger.info(" Freshsales CRM Continuous Upsert Watcher Active")
        logger.info("=" * 70)
        logger.info(f"Watching Input:   {input_dir}")
        logger.info(f"Writing Reports:  {reports_dir}")
        logger.info(f"SQLite DB:        {settings.data_dir / 'crm_automation.db'}")
        logger.info(f"Logs File:        {settings.data_dir.parent / 'logs' / 'agent.log'}")
        logger.info(f"Auto-delete:      {'Enabled' if self.auto_delete_input else 'Disabled'}")
        logger.info("=" * 70)
        logger.info("Waiting for Good email files to arrive... (Press Ctrl+C to stop)\n")

        try:
            while True:
                files = self.find_input_files(input_dir)
                if files:
                    current_file = files[0]
                    logger.info(f"[Queue] Found '{current_file.name}' ({len(files) - 1} more in queue). Starting processing...")
                    self.process_file(current_file, reports_dir)
                    continue

                time.sleep(settings.watch_interval_seconds)
        except KeyboardInterrupt:
            logger.info("[Watcher] Automation agent stopped by user.")
