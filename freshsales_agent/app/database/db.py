from __future__ import annotations

from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.database.models import Base

# Ensure data directory exists
settings.data_dir.mkdir(parents=True, exist_ok=True)
db_file = settings.data_dir / "crm_automation.db"

DATABASE_URL = f"sqlite:///{db_file.resolve()}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Initializes SQLite database tables."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    """Yields a database session."""
    db = SessionLocal()
    try:
        return db
    finally:
        pass
