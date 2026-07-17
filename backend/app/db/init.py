"""Database bootstrap: run migrations and seed default local data."""

from __future__ import annotations

import os
from pathlib import Path

from alembic.config import Config
from sqlalchemy.orm import Session

from alembic import command

from ..config import get_settings
from ..logging import get_logger
from .base import Base, get_engine, session_scope
from .models import EnvironmentProfile, Project, ProviderProfile

log = get_logger(__name__)
_BACKEND_DIR = Path(__file__).resolve().parents[2]


def run_migrations() -> None:
    """Upgrade the local SQLite database to head."""
    get_settings().ensure_dirs()
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")


def create_all() -> None:
    """Create tables directly (used by the test suite for speed)."""
    Base.metadata.create_all(get_engine())


def seed_defaults(session: Session) -> Project:
    """Ensure a default project, a demo environment and a default provider exist."""
    project = session.query(Project).filter_by(is_default=True).first()
    if project is None:
        project = Project(
            name="Demo Project",
            description="Local sandbox seeded with a fixture Planning application (MCWPCF).",
            is_default=True,
        )
        session.add(project)
        session.flush()

    if not session.query(EnvironmentProfile).filter_by(project_id=project.id).count():
        session.add(
            EnvironmentProfile(
                project_id=project.id,
                name="MCW Demo (Local)",
                base_url=None,
                username="demo",
                auth_method="demo",
                classification="development",
                preferred_application="MCWPCF",
                demo=True,
            )
        )

    # Default deterministic local AI provider — no network, no key required.
    if not session.query(ProviderProfile).filter_by(provider_type="mock").count():
        session.add(
            ProviderProfile(
                name="EPM Wizard Local (Deterministic)",
                provider_type="mock",
                default_model="epmw-local-1",
                models=["epmw-local-1"],
                role_models={},
                enabled=True,
                has_key=False,
            )
        )

    _seed_from_env(session, project)
    return project


def _seed_from_env(session: Session, project: Project) -> None:
    """Pre-populate a real Oracle profile / Anthropic provider from env, for
    convenience only. Passwords are never stored here — the user still connects
    via the UI, which places credentials in the secret store / process memory."""
    if os.environ.get("EPMW_DISABLE_ENV_SEED"):
        return
    instance = os.environ.get("INSTANCE") or os.environ.get("EPMW_INSTANCE")
    username = os.environ.get("USERNAME") or os.environ.get("EPMW_ORACLE_USERNAME")
    if instance and username and not session.query(EnvironmentProfile).filter_by(demo=False, project_id=project.id).first():
        classification = "test" if "test" in instance.lower() else (
            "production" if "prod" in instance.lower() else "development"
        )
        session.add(
            EnvironmentProfile(
                project_id=project.id,
                name="MCW (from environment)",
                base_url=instance.rstrip("/"),
                username=username,
                auth_method="passwordInMemory",
                classification=classification,
                preferred_application="MCWPCF",
                demo=False,
            )
        )
        log.info("seeded_real_environment", classification=classification)

    has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY"))
    if has_anthropic and not session.query(ProviderProfile).filter_by(provider_type="anthropic").first():
        session.add(
            ProviderProfile(
                name="Anthropic (from environment)",
                provider_type="anthropic",
                base_url="https://api.anthropic.com",
                default_model="claude-sonnet-5",
                models=["claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5-20251001"],
                role_models={},
                enabled=True,
                has_key=True,  # resolved from env at call time; never copied into the DB
            )
        )


def initialize(seed: bool = True) -> None:
    run_migrations()
    if seed:
        with session_scope() as session:
            seed_defaults(session)
