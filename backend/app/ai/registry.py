"""Provider registry: instantiate an AIProvider from a stored profile, resolving
the API key from the encrypted secret store (or an env fallback). Keys are never
logged, never persisted to SQLite, never sent to the model."""

from __future__ import annotations

import os

from sqlalchemy.orm import Session

from ..db.models import ProviderProfile
from ..security import get_secret_store
from .anthropic import AnthropicProvider
from .base import AIProvider, ProviderConfig
from .gemini import GeminiProvider
from .mock import MockProvider
from .openai_compat import OpenAICompatibleProvider
from .watsonx import WatsonxProvider

SECRET_NS = "provider"

_ENV_KEYS = {
    "anthropic": ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
    "openrouter": ["OPENROUTER_API_KEY"],
    "together": ["TOGETHER_API_KEY"],
    "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "watsonx": ["WATSONX_API_KEY", "IBM_CLOUD_API_KEY"],
}


def _class_for(provider_type: str) -> type[AIProvider]:
    if provider_type == "mock":
        return MockProvider
    if provider_type == "anthropic":
        return AnthropicProvider
    if provider_type in ("gemini", "google"):
        return GeminiProvider
    if provider_type in ("watsonx", "ibm"):
        return WatsonxProvider
    return OpenAICompatibleProvider  # openai | openrouter | ollama | generic


def _resolve_key(provider_id: str, provider_type: str) -> str | None:
    stored = get_secret_store().get(SECRET_NS, provider_id)
    if stored:
        return stored
    for env_name in _ENV_KEYS.get(provider_type, []):
        if os.environ.get(env_name):
            return os.environ[env_name]
    return None


def provider_from_profile(profile: ProviderProfile) -> AIProvider:
    config = ProviderConfig(
        provider_type=profile.provider_type,
        base_url=profile.base_url,
        api_key=_resolve_key(profile.id, profile.provider_type),
        default_model=profile.default_model,
        models=profile.models or [],
        role_models=profile.role_models or {},
    )
    return _class_for(profile.provider_type)(config)


def resolve_active_provider(session: Session, project_id: str | None = None) -> tuple[ProviderProfile | None, AIProvider]:
    """Return the profile + provider to use. Falls back to the mock provider so
    chat always works, even with no configuration."""
    profiles = session.query(ProviderProfile).filter_by(enabled=True).all()
    chosen: ProviderProfile | None = None
    if project_id:
        from ..services.settings_svc import get_setting
        pid = get_setting(session, "activeProviderId", project_id=project_id)
        if pid:
            chosen = next((p for p in profiles if p.id == pid), None)
    if chosen is None:
        # prefer a configured external provider, else the mock
        chosen = next((p for p in profiles if p.provider_type != "mock" and p.has_key), None)
        chosen = chosen or next((p for p in profiles if p.provider_type == "mock"), None)
        chosen = chosen or (profiles[0] if profiles else None)
    if chosen is None:
        return None, MockProvider()
    return chosen, provider_from_profile(chosen)
