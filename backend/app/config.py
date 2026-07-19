"""Application configuration and local data-directory layout.

Everything EPM Wizard persists lives under ``data_dir`` (a named Docker volume in
compose, a local folder for dev). No hosted database, no cloud storage.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _load_dotenv() -> None:
    """Populate os.environ from the nearest ``.env`` (repo root) for local runs.

    Docker Compose injects these via ``env_file`` instead. Values are the user's
    explicit app config, so they override the ambient environment. Nothing here
    is ever logged.
    """
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        candidate = parent / ".env"
        if candidate.exists():
            try:
                for raw in candidate.read_text(encoding="utf-8").splitlines():
                    line = raw.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key:
                        os.environ[key] = value
            except OSError:
                pass
            return


_load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EPMW_", extra="ignore")

    app_name: str = "EPM Wizard"
    version: str = "0.1.0"

    data_dir: Path = Field(default_factory=lambda: Path(os.environ.get("EPMW_DATA_DIR", "./data")))
    log_level: str = "INFO"
    log_json: bool = True

    # Comma-separated list is also accepted via env.
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Optional stable key for the local encrypted secret store. If empty a key is
    # generated and stored (0600) on first run.
    secret_master_key: str = ""

    # Optional EPM Automate runner (Oracle software is never redistributed here).
    epmautomate_path: str = ""
    java_home: str = ""
    # Name of a saved "Export Metadata" job in the Planning app. Member/dimension
    # enumeration is not exposed by the Planning REST API, so members are imported
    # by running this job via EPM Automate, then downloading + parsing the export.
    oracle_metadata_job: str = ""
    # Alternative to a saved job: the name of an existing LCM application snapshot
    # (e.g. "Artifact Snapshot") to download and parse members from — no job to
    # create. Used only when oracle_metadata_job is unset.
    oracle_metadata_snapshot: str = ""

    # Default provider/model for a fresh install: the deterministic local mock so
    # the app is fully usable with zero configuration and no network.
    default_provider: str = "mock"
    default_model: str = "epmw-local-1"

    # How many timestamped SQLite backups to keep in <data>/backups (EPMW_BACKUP_KEEP).
    backup_keep: int = 5

    # Optional external database (EPMW_DATABASE_URL). When set it wins over the
    # local SQLite file — e.g. IBM Cloud Databases for PostgreSQL:
    #   postgresql+psycopg://user:pass@host:port/db?sslmode=verify-full&sslrootcert=/path/ca.pem
    # When empty (the default) the app uses sqlite:///<data>/epmwizard.db exactly
    # as before.
    database_url: str = ""

    @property
    def db_path(self) -> Path:
        return self.data_dir / "epmwizard.db"

    @property
    def db_url(self) -> str:
        """Effective SQLAlchemy URL: EPMW_DATABASE_URL if set, else local SQLite."""
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.db_path}"

    @property
    def is_sqlite(self) -> bool:
        return self.db_url.startswith("sqlite")

    @property
    def artifacts_dir(self) -> Path:
        return self.data_dir / "artifacts"

    @property
    def contexts_dir(self) -> Path:
        return self.data_dir / "contexts"

    @property
    def secrets_dir(self) -> Path:
        return self.data_dir / "secrets"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def runner_dir(self) -> Path:
        return self.data_dir / "runner"

    @property
    def tmp_dir(self) -> Path:
        return self.data_dir / "tmp"

    def ensure_dirs(self) -> None:
        for p in (
            self.data_dir,
            self.artifacts_dir,
            self.contexts_dir,
            self.secrets_dir,
            self.runner_dir,
            self.tmp_dir,
            self.backups_dir,
        ):
            p.mkdir(parents=True, exist_ok=True)
        # Lock down the secrets directory where the OS supports it.
        try:
            os.chmod(self.secrets_dir, 0o700)
        except OSError:
            pass


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
