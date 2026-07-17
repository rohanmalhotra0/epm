"""AI provider profile persistence (spec section 11). API keys go to the
encrypted secret store, never to SQLite."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..db.models import ProviderProfile
from ..schemas.api import ProviderOut
from ..security import get_secret_store

SECRET_NS = "provider"


def to_out(p: ProviderProfile) -> ProviderOut:
    return ProviderOut(
        id=p.id,
        name=p.name,
        provider_type=p.provider_type,
        base_url=p.base_url,
        default_model=p.default_model,
        models=p.models or [],
        role_models=p.role_models or {},
        enabled=p.enabled,
        has_key=p.has_key,
    )


def list_providers(session: Session) -> list[ProviderProfile]:
    return session.query(ProviderProfile).order_by(ProviderProfile.created_at.asc()).all()


def get_provider(session: Session, provider_id: str) -> ProviderProfile | None:
    return session.get(ProviderProfile, provider_id)


def create_provider(
    session: Session,
    name: str,
    provider_type: str,
    base_url: str | None = None,
    default_model: str | None = None,
    api_key: str | None = None,
    role_models: dict | None = None,
) -> ProviderProfile:
    provider = ProviderProfile(
        name=name,
        provider_type=provider_type,
        base_url=base_url,
        default_model=default_model,
        role_models=role_models or {},
        has_key=bool(api_key),
    )
    session.add(provider)
    session.flush()
    if api_key:
        get_secret_store().set(SECRET_NS, provider.id, api_key)
    return provider


def set_api_key(session: Session, provider_id: str, api_key: str) -> None:
    provider = session.get(ProviderProfile, provider_id)
    if provider is None:
        raise KeyError("provider not found")
    get_secret_store().set(SECRET_NS, provider_id, api_key)
    provider.has_key = True


def get_api_key(provider_id: str) -> str | None:
    return get_secret_store().get(SECRET_NS, provider_id)


def update_provider(session: Session, provider_id: str, **fields) -> ProviderProfile | None:
    provider = session.get(ProviderProfile, provider_id)
    if provider is None:
        return None
    for key in ("name", "base_url", "default_model", "enabled", "role_models", "models"):
        if key in fields and fields[key] is not None:
            setattr(provider, key, fields[key])
    return provider


def delete_provider(session: Session, provider_id: str) -> None:
    provider = session.get(ProviderProfile, provider_id)
    if provider is not None:
        get_secret_store().delete(SECRET_NS, provider_id)
        session.delete(provider)
