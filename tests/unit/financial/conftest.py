"""Shared fixtures for financial coverage tests — tmp SQLite DB isolation."""

import os

import pytest

# Allow phone hashing if needed by any transitive import
os.environ.setdefault("BRIDGE_ALLOW_INSECURE_SALT", "1")


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Provide an isolated tmp SQLite DB with v3.0 schema for each test."""
    db_path = tmp_path / "test_financial_coverage.db"
    monkeypatch.setattr("src.financial.database.DB_PATH", str(db_path))
    from src.financial.database import init_database_v3

    init_database_v3()
    return str(db_path)
