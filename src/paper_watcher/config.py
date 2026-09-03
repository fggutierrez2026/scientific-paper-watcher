import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Ruta raíz del proyecto
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Cargar variables desde .env
load_dotenv(PROJECT_ROOT / ".env")

@dataclass(frozen=True)
class Config:
    database_path: Path
    report_dir: Path
    request_timeout: int
    max_retries: int
    ncbi_email: str
    ncbi_api_key: str | None = None

def load_config() -> Config:
    database_path = PROJECT_ROOT / (
        os.getenv("PAPER_WATCHER_DB")
        or os.getenv("DATABASE_PATH")
        or "data/papers.db"
    )

    report_dir = PROJECT_ROOT / (
        os.getenv("PAPER_WATCHER_REPORT_DIR")
        or os.getenv("REPORT_DIR")
        or "reports"
    )

    request_timeout = int(
        os.getenv("REQUEST_TIMEOUT", "15")
    )

    max_retries = int(
        os.getenv("MAX_RETRIES", "3")
    )

    ncbi_email = (
        os.getenv("NCBI_EMAIL")
        or os.getenv("PUBMED_EMAIL")
        or ""
    )

    ncbi_api_key = (
        os.getenv("NCBI_API_KEY")
        or os.getenv("PUBMED_API_KEY")
        or None
    )

    return Config(
        database_path=database_path,
        report_dir=report_dir,
        request_timeout=request_timeout,
        max_retries=max_retries,
        ncbi_email=ncbi_email,
        ncbi_api_key=ncbi_api_key,
    )
