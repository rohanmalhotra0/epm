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
    """Upgrade the effective database (local SQLite or EPMW_DATABASE_URL) to head."""
    get_settings().ensure_dirs()
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")


def create_all() -> None:
    """Create tables directly (used by the test suite for speed)."""
    Base.metadata.create_all(get_engine())


def seed_defaults(session: Session) -> Project:
    """Ensure a default project and a default provider exist.

    No demo environment is ever seeded: the app starts on a sign-in screen and
    only ever connects to a real Oracle EPM tenant that the user supplies.
    """
    project = session.query(Project).filter_by(is_default=True).first()
    if project is None:
        project = Project(
            name="Default Project",
            description="Local project. Sign in to an Oracle EPM environment to begin.",
            is_default=True,
            owner_id="local",
        )
        session.add(project)
        session.flush()

    # Purge any demo environment left over from earlier versions (the app no
    # longer seeds one and only ever connects to a real Oracle EPM tenant).
    demo_envs = session.query(EnvironmentProfile).filter_by(demo=True).all()
    if demo_envs:
        demo_ids = {e.id for e in demo_envs}
        for proj in session.query(Project).all():
            if proj.active_environment_id in demo_ids:
                proj.active_environment_id = None
        for env in demo_envs:
            session.delete(env)
        session.flush()

    # Heal real environments still pointing at the demo application placeholder
    # ("MCWPCF") — it 404s against a real tenant. It is re-discovered on connect.
    session.query(EnvironmentProfile).filter_by(demo=False, preferred_application="MCWPCF").update(
        {"preferred_application": None}
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
                preferred_application=None,  # discovered from the tenant on connect
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

    # Together AI (the Fly.io / cheap-open-model deployment): when
    # TOGETHER_API_KEY is injected, auto-seed a ready-to-use provider so the
    # hosted app runs on Together out of the box. Model ids are env-overridable
    # (Together's catalog changes — verify with "Detect models" in Settings).
    # The key is resolved from the env at call time, never copied into the DB.
    together_key = bool(os.environ.get("TOGETHER_API_KEY"))
    if together_key and not session.query(ProviderProfile).filter_by(provider_type="together").first():
        code_model = os.environ.get("TOGETHER_CODE_MODEL") or "Qwen/Qwen2.5-Coder-32B-Instruct"
        chat_model = os.environ.get("TOGETHER_CHAT_MODEL") or code_model
        vision_model = os.environ.get("TOGETHER_VISION_MODEL") or "Qwen/Qwen2.5-VL-72B-Instruct"
        embed_model = os.environ.get("TOGETHER_EMBEDDINGS_MODEL") or "BAAI/bge-base-en-v1.5"
        base = os.environ.get("TOGETHER_URL") or "https://api.together.xyz/v1"
        session.add(
            ProviderProfile(
                name="Together AI (from environment)",
                provider_type="together",
                base_url=base,
                default_model=chat_model,
                models=[chat_model, code_model],
                role_models={"chat": chat_model, "fast": chat_model, "structured": code_model,
                             "code": code_model, "vision": vision_model, "embedding": embed_model},
                enabled=True,
                has_key=True,  # resolved from env (TOGETHER_API_KEY) at call time
            )
        )


def initialize(seed: bool = True, migrate: bool = True) -> None:
    if migrate:
        run_migrations()
    if seed:
        with session_scope() as session:
            seed_defaults(session)
