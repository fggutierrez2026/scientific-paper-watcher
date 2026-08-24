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

def load_config() -> Config:
    database_path = PROJECT_ROOT / os.getenv(
        "PAPER_WATCHER_DB",
        "data/papers.pdb",
    )

    report_dir = PROJECT_ROOT / os.getenv(
        "PAPER_WATCHER_REPORT_DIR",
        "reports",
    )

    request_timeout = int(
        os.getenv("REQUEST_TIMEOUT", "15",)
    )

    max_retries = int(
        os.getenv("MAX_RETRIES", "3",)
    )

    return Config(
        database_path=database_path,
        report_dir=report_dir,
        request_timeout=request_timeout,
        max_retries=max_retries,
    )
