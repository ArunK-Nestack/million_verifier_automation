from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class FileRunMetric(Base):
    __tablename__ = "file_run_metrics"

    run_id = Column(Integer, primary_key=True, autoincrement=True)
    started_at = Column(String(50), nullable=False)
    completed_at = Column(String(50), nullable=True)
    source_filename = Column(String(255), nullable=False)
    tag_applied = Column(String(255), nullable=False)
    apollo_login_owner = Column(String(255), nullable=True)
    total_input_rows = Column(Integer, default=0)
    file_duplicates_skipped = Column(Integer, default=0)
    tld_filtered_count = Column(Integer, default=0)
    contacts_sent_to_crm = Column(Integer, default=0)
    freshly_created_count = Column(Integer, default=0)
    updated_in_crm_count = Column(Integer, default=0)
    failed_errors_count = Column(Integer, default=0)
    updated_percentage = Column(Float, default=0.0)
    overall_success_percentage = Column(Float, default=0.0)
    status = Column(String(50), default="in_progress")
    report_file_path = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    audit_records = relationship("ContactAuditTrail", back_populates="run_metric", cascade="all, delete-orphan")


class ContactAuditTrail(Base):
    __tablename__ = "contact_audit_trail"

    audit_id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("file_run_metrics.run_id"), nullable=False)
    email = Column(String(255), nullable=False)
    action = Column(String(50), nullable=False)  # 'created', 'updated', 'skipped_duplicate', 'excluded_tld', 'failed'
    fields_filled_count = Column(Integer, default=0)
    fields_filled_names = Column(Text, nullable=True)
    error_reason = Column(Text, nullable=True)
    created_at = Column(String(50), default=lambda: datetime.now().isoformat())

    run_metric = relationship("FileRunMetric", back_populates="audit_records")
