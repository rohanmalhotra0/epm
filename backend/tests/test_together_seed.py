"""Together environment-provider defaults and retirement self-healing."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.init import _seed_from_env
from app.db.models import Project, ProviderProfile


def _session_with_project() -> tuple[Session, Project]:
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    session = Session(engine)
    project = Project(name="test", is_default=True, owner_id="local")
    session.add(project)
    session.flush()
    return session, project


def test_together_env_seed_uses_current_serverless_vision_and_embedding(monkeypatch):
    monkeypatch.delenv("EPMW_DISABLE_ENV_SEED", raising=False)
    monkeypatch.setenv("TOGETHER_API_KEY", "test-key")
    session, project = _session_with_project()
    try:
        _seed_from_env(session, project)
        profile = session.query(ProviderProfile).filter_by(provider_type="together").one()
        assert profile.role_models["vision"] == "Qwen/Qwen3.5-9B"
        assert (
            profile.role_models["embedding"]
            == "intfloat/multilingual-e5-large-instruct"
        )
    finally:
        session.close()


def test_together_env_seed_self_heals_retired_role_models_only(monkeypatch):
    monkeypatch.delenv("EPMW_DISABLE_ENV_SEED", raising=False)
    monkeypatch.setenv("TOGETHER_API_KEY", "test-key")
    session, project = _session_with_project()
    try:
        profile = ProviderProfile(
            name="Together AI (from environment)",
            provider_type="together",
            base_url="https://api.together.xyz/v1",
            default_model="openai/gpt-oss-120b",
            models=["openai/gpt-oss-120b"],
            role_models={
                "chat": "openai/gpt-oss-120b",
                "code": "openai/gpt-oss-120b",
                "vision": "Qwen/Qwen2.5-VL-72B-Instruct",
                "embedding": "BAAI/bge-base-en-v1.5",
                "custom": "preserved",
            },
            enabled=True,
            has_key=True,
        )
        session.add(profile)
        session.flush()

        _seed_from_env(session, project)

        assert profile.role_models["vision"] == "Qwen/Qwen3.5-9B"
        assert (
            profile.role_models["embedding"]
            == "intfloat/multilingual-e5-large-instruct"
        )
        assert profile.role_models["custom"] == "preserved"
        assert profile.default_model == "openai/gpt-oss-120b"
    finally:
        session.close()


def test_together_env_seed_never_rewrites_user_created_profile(monkeypatch):
    monkeypatch.delenv("EPMW_DISABLE_ENV_SEED", raising=False)
    monkeypatch.setenv("TOGETHER_API_KEY", "test-key")
    session, project = _session_with_project()
    try:
        profile = ProviderProfile(
            name="My dedicated Together endpoint",
            provider_type="together",
            base_url="https://dedicated.example/v1",
            default_model="custom-chat",
            models=["custom-chat"],
            role_models={"vision": "Qwen/Qwen2.5-VL-72B-Instruct"},
            enabled=True,
            has_key=True,
        )
        session.add(profile)
        session.flush()

        _seed_from_env(session, project)

        assert profile.role_models["vision"] == "Qwen/Qwen2.5-VL-72B-Instruct"
        assert profile.default_model == "custom-chat"
    finally:
        session.close()
