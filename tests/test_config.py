from __future__ import annotations

import os
from unittest.mock import patch

from paper_watcher.config import load_config


def test_default_config(tmp_path):
    with patch.dict(os.environ, {}, clear=True):
        cfg = load_config()
        assert str(cfg.database_path).endswith("data/papers.db")
        assert str(cfg.report_dir).endswith("reports")
        assert cfg.request_timeout == 15
        assert cfg.max_retries == 3
        assert cfg.ncbi_email == ""
        assert cfg.ncbi_api_key is None


def test_config_with_custom_env():
    custom_env = {
        "PAPER_WATCHER_DB": "custom_data/custom.db",
        "PAPER_WATCHER_REPORT_DIR": "custom_reports",
        "REQUEST_TIMEOUT": "30",
        "MAX_RETRIES": "5",
        "NCBI_EMAIL": "researcher@example.org",
        "NCBI_API_KEY": "my_api_key_123",
    }
    with patch.dict(os.environ, custom_env, clear=True):
        cfg = load_config()
        assert str(cfg.database_path).endswith("custom_data/custom.db")
        assert str(cfg.report_dir).endswith("custom_reports")
        assert cfg.request_timeout == 30
        assert cfg.max_retries == 5
        assert cfg.ncbi_email == "researcher@example.org"
        assert cfg.ncbi_api_key == "my_api_key_123"


def test_config_with_legacy_aliases():
    legacy_env = {
        "DATABASE_PATH": "legacy/papers.db",
        "REPORT_DIR": "legacy_reports",
        "PUBMED_EMAIL": "legacy@example.org",
        "PUBMED_API_KEY": "legacy_key",
    }
    with patch.dict(os.environ, legacy_env, clear=True):
        cfg = load_config()
        assert str(cfg.database_path).endswith("legacy/papers.db")
        assert str(cfg.report_dir).endswith("legacy_reports")
        assert cfg.ncbi_email == "legacy@example.org"
        assert cfg.ncbi_api_key == "legacy_key"

