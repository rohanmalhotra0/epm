"""PostgreSQL support unit tests — no live server required.

Covers the EPMW_DATABASE_URL override, ``Settings.is_sqlite``, dialect-aware
engine kwargs, the honest degradation of SQLite-only features (file backups)
and the credential-free diagnostics label.
"""

from __future__ import annotations

import pytest

from app.api import routes_diagnostics
from app.config import Settings
from app.db.base import engine_kwargs
from app.services import backups as backups_svc

PG_URL = "postgresql+psycopg://epmw:s3cret@db.example.com:31234/epmwizard?sslmode=verify-full"


# --- Settings: URL precedence + is_sqlite ------------------------------------


def test_default_db_url_is_local_sqlite():
    s = Settings(database_url="")
    assert s.db_url == f"sqlite:///{s.data_dir / 'epmwizard.db'}"
    assert s.is_sqlite is True


def test_database_url_wins_over_sqlite_path():
    s = Settings(database_url=PG_URL)
    assert s.db_url == PG_URL
    assert s.is_sqlite is False


def test_database_url_env_override(monkeypatch):
    monkeypatch.setenv("EPMW_DATABASE_URL", PG_URL)
    s = Settings()
    assert s.db_url == PG_URL and not s.is_sqlite


# --- Engine kwargs branching --------------------------------------------------


def test_engine_kwargs_sqlite_keeps_check_same_thread():
    kwargs = engine_kwargs("sqlite:////data/epmwizard.db")
    assert kwargs["connect_args"] == {"check_same_thread": False}
    assert "pool_pre_ping" not in kwargs


def test_engine_kwargs_postgres_pool_settings():
    kwargs = engine_kwargs(PG_URL)
    assert kwargs["pool_pre_ping"] is True
    assert kwargs["pool_size"] >= 1 and kwargs["max_overflow"] >= 0
    # Bounded connect: a hung database must fail fast, not stall startup forever.
    assert kwargs["connect_args"]["connect_timeout"] >= 1
    assert "check_same_thread" not in kwargs["connect_args"]  # SQLite-only arg


# --- Backups degrade honestly on a managed database --------------------------


def _pg_settings() -> Settings:
    return Settings(database_url=PG_URL)


def test_create_backup_refuses_on_postgres(monkeypatch):
    monkeypatch.setattr(backups_svc, "get_settings", _pg_settings)
    with pytest.raises(backups_svc.ManagedDatabaseError, match="managed database"):
        backups_svc.create_backup()


def test_list_backups_empty_on_postgres(monkeypatch):
    monkeypatch.setattr(backups_svc, "get_settings", _pg_settings)
    assert backups_svc.list_backups() == []


# --- Diagnostics subsystem label ----------------------------------------------


def test_database_subsystem_sqlite(monkeypatch):
    s = Settings(database_url="")
    monkeypatch.setattr(routes_diagnostics, "get_settings", lambda: s)
    name, detail = routes_diagnostics._database_subsystem()
    assert name == "SQLite database"
    assert detail.endswith("epmwizard.db")


def test_database_subsystem_postgres_hides_credentials(monkeypatch):
    monkeypatch.setattr(routes_diagnostics, "get_settings", _pg_settings)
    name, detail = routes_diagnostics._database_subsystem()
    assert name == "PostgreSQL database"
    assert detail == "db.example.com:31234/epmwizard"
    assert "epmw:" not in detail and "s3cret" not in detail
