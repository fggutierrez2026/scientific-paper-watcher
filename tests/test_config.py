from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from paper_watcher.config import (
    DEFAULT_PAPER_SOURCES,
    Config,
    load_config,
    source_is_enabled,
    validate_source_access,
)
from paper_watcher.exceptions import ConfigurationError


def test_default_config(tmp_path):
    with patch.dict(os.environ, {}, clear=True):
        cfg = load_config()
        assert str(cfg.database_path).endswith("data/papers.db")
        assert str(cfg.report_dir).endswith("reports")
        assert cfg.request_timeout == 15
        assert cfg.max_retries == 3
        assert cfg.ncbi_email == ""
        assert cfg.ncbi_api_key is None
        assert cfg.biorxiv_interval == "30d"
        assert cfg.openalex_enabled is False
        assert cfg.openalex_api_key is None
        assert cfg.paper_sources == DEFAULT_PAPER_SOURCES
        assert cfg.patent_sources == ()
        assert cfg.semantic_scholar_api_key is None
        assert cfg.crossref_email is None
        assert cfg.core_api_key is None
        assert cfg.unpaywall_email is None
        assert cfg.lens_api_token is None
        assert cfg.uspto_api_key is None
        assert cfg.epo_consumer_key is None
        assert cfg.epo_consumer_secret is None
        assert cfg.wipo_username is None
        assert cfg.wipo_password is None


def test_config_with_custom_env():
    custom_env = {
        "PAPER_WATCHER_DB": "custom_data/custom.db",
        "PAPER_WATCHER_REPORT_DIR": "custom_reports",
        "REQUEST_TIMEOUT": "30",
        "MAX_RETRIES": "5",
        "NCBI_EMAIL": "researcher@example.org",
        "NCBI_API_KEY": "my_api_key_123",
        "BIORXIV_INTERVAL": "14d",
        "OPENALEX_ENABLED": "true",
        "OPENALEX_API_KEY": "test-openalex-key",
        "PAPER_SOURCES": "pubmed, semantic-scholar, core, pubmed",
        "PATENT_SOURCES": "uspto, epo, lens, wipo",
        "SEMANTIC_SCHOLAR_API_KEY": "test-semantic-scholar-key",
        "CROSSREF_EMAIL": "crossref@example.org",
        "CORE_API_KEY": "test-core-key",
        "UNPAYWALL_EMAIL": "unpaywall@example.org",
        "LENS_API_TOKEN": "test-lens-token",
        "USPTO_API_KEY": "test-uspto-key",
        "EPO_CONSUMER_KEY": "test-epo-key",
        "EPO_CONSUMER_SECRET": "test-epo-secret",
        "WIPO_USERNAME": "test-wipo-user",
        "WIPO_PASSWORD": "test-wipo-password",
    }
    with patch.dict(os.environ, custom_env, clear=True):
        cfg = load_config()
        assert str(cfg.database_path).endswith("custom_data/custom.db")
        assert str(cfg.report_dir).endswith("custom_reports")
        assert cfg.request_timeout == 30
        assert cfg.max_retries == 5
        assert cfg.ncbi_email == "researcher@example.org"
        assert cfg.ncbi_api_key == "my_api_key_123"
        assert cfg.biorxiv_interval == "14d"
        assert cfg.openalex_enabled is True
        assert cfg.openalex_api_key == "test-openalex-key"
        assert cfg.paper_sources == ("pubmed", "semantic_scholar", "core")
        assert cfg.patent_sources == ("uspto", "epo", "lens", "wipo")
        assert cfg.semantic_scholar_api_key == "test-semantic-scholar-key"
        assert cfg.crossref_email == "crossref@example.org"
        assert cfg.core_api_key == "test-core-key"
        assert cfg.unpaywall_email == "unpaywall@example.org"
        assert cfg.lens_api_token == "test-lens-token"
        assert cfg.uspto_api_key == "test-uspto-key"
        assert cfg.epo_consumer_key == "test-epo-key"
        assert cfg.epo_consumer_secret == "test-epo-secret"
        assert cfg.wipo_username == "test-wipo-user"
        assert cfg.wipo_password == "test-wipo-password"


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


def test_empty_source_lists_disable_all_sources():
    with patch.dict(
        os.environ,
        {"PAPER_SOURCES": "", "PATENT_SOURCES": ""},
        clear=True,
    ):
        cfg = load_config()

    assert cfg.paper_sources == ()
    assert cfg.patent_sources == ()


def test_unknown_source_is_rejected():
    with patch.dict(os.environ, {"PAPER_SOURCES": "pubmed,unknown"}, clear=True):
        with pytest.raises(ConfigurationError, match="Unknown source 'unknown'"):
            load_config()


def test_disabled_source_does_not_require_credentials():
    with patch.dict(os.environ, {}, clear=True):
        cfg = load_config()

    assert source_is_enabled(cfg, "core", "paper") is False
    with pytest.raises(ConfigurationError, match="Add it to PAPER_SOURCES"):
        validate_source_access(cfg, "core", "paper")


def test_enabled_source_reports_missing_setting_without_a_secret_value():
    secret = "must-never-appear-in-errors"
    with patch.dict(
        os.environ,
        {
            "PATENT_SOURCES": "epo",
            "EPO_CONSUMER_KEY": secret,
        },
        clear=True,
    ):
        cfg = load_config()

    with pytest.raises(ConfigurationError) as error:
        validate_source_access(cfg, "epo", "patent")

    message = str(error.value)
    assert "EPO_CONSUMER_SECRET" in message
    assert "epo.org" in message
    assert secret not in message


def test_enabled_source_with_required_access_passes_validation():
    with patch.dict(
        os.environ,
        {
            "PAPER_SOURCES": "core,semantic_scholar",
            "CORE_API_KEY": "configured-core-key",
        },
        clear=True,
    ):
        cfg = load_config()

    validate_source_access(cfg, "core", "paper")
    # Semantic Scholar supports unauthenticated access, so its key is optional.
    validate_source_access(cfg, "semantic_scholar", "paper")


def test_config_repr_redacts_credentials_and_private_contacts():
    values = {
        "NCBI_EMAIL": "private-ncbi@example.org",
        "NCBI_API_KEY": "secret-ncbi",
        "OPENALEX_API_KEY": "secret-openalex",
        "SEMANTIC_SCHOLAR_API_KEY": "secret-semantic-scholar",
        "CROSSREF_EMAIL": "private-crossref@example.org",
        "CORE_API_KEY": "secret-core",
        "UNPAYWALL_EMAIL": "private-unpaywall@example.org",
        "LENS_API_TOKEN": "secret-lens",
        "USPTO_API_KEY": "secret-uspto",
        "EPO_CONSUMER_KEY": "secret-epo-key",
        "EPO_CONSUMER_SECRET": "secret-epo-secret",
        "WIPO_USERNAME": "private-wipo-user",
        "WIPO_PASSWORD": "secret-wipo-password",
    }
    with patch.dict(os.environ, values, clear=True):
        cfg = load_config()

    rendered = repr(cfg)
    for value in values.values():
        assert value not in rendered


def test_source_kind_uses_independent_paper_and_patent_policies():
    config = Config(
        database_path=load_config().database_path,
        report_dir=load_config().report_dir,
        request_timeout=15,
        max_retries=3,
        ncbi_email="",
        paper_sources=("lens",),
        patent_sources=(),
        lens_api_token="configured-token",
    )

    assert source_is_enabled(config, "lens", "paper") is True
    assert source_is_enabled(config, "lens", "patent") is False
    validate_source_access(config, "lens", "paper")
    with pytest.raises(ConfigurationError, match="PATENT_SOURCES"):
        validate_source_access(config, "lens", "patent")
