from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    api_key: str
    bulk_base_url: str
    poll_interval_seconds: int
    watch_interval_seconds: int
    delete_input_file: bool
    http_timeout_seconds: int
    default_input_dir: Path
    default_output_dir: Path

    def require_api_key(self) -> None:
        if not self.api_key or self.api_key == "replace_with_your_real_api_key":
            raise RuntimeError(
                "MILLIONVERIFIER_API_KEY is not configured. "
                "Add your API key to .env file."
            )


settings = Settings(
    api_key=os.getenv("MILLIONVERIFIER_API_KEY", "").strip(),
    bulk_base_url=os.getenv(
        "MILLIONVERIFIER_BULK_BASE_URL",
        "https://bulkapi.millionverifier.com",
    ).rstrip("/"),
    poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "60")),
    watch_interval_seconds=int(os.getenv("WATCH_INTERVAL_SECONDS", "15")),
    delete_input_file=os.getenv("DELETE_INPUT_FILE", "true").lower() in ("true", "1", "yes"),
    http_timeout_seconds=int(os.getenv("HTTP_TIMEOUT_SECONDS", "60")),
    default_input_dir=Path(
        os.getenv(
            "INPUT_DIR",
            r"G:\My Drive\million automation\million input",
        )
    ),
    default_output_dir=Path(
        os.getenv(
            "OUTPUT_DIR",
            r"G:\My Drive\million automation\million output",
        )
    ),
)
