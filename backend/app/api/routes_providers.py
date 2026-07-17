"""AI provider routes (spec section 11)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..ai.base import ProviderError
from ..ai.registry import provider_from_profile
from ..schemas.api import ProviderCreate, ProviderOut
from ..services import providers as svc
from .deps import get_db

router = APIRouter(prefix="/api/providers", tags=["providers"])


@router.get("", response_model=list[ProviderOut])
def list_providers(session: Session = Depends(get_db)) -> list[ProviderOut]:
    return [svc.to_out(p) for p in svc.list_providers(session)]


@router.post("", response_model=ProviderOut, status_code=201)
def create_provider(body: ProviderCreate, session: Session = Depends(get_db)) -> ProviderOut:
    provider = svc.create_provider(session, name=body.name, provider_type=body.provider_type,
                                   base_url=body.base_url, default_model=body.default_model,
                                   api_key=body.api_key, role_models=body.role_models)
    return svc.to_out(provider)


@router.patch("/{provider_id}", response_model=ProviderOut)
def update_provider(provider_id: str, body: dict, session: Session = Depends(get_db)) -> ProviderOut:
    if "apiKey" in body or "api_key" in body:
        svc.set_api_key(session, provider_id, body.get("apiKey") or body.get("api_key"))
    fields = {k: body[k] for k in ("name", "baseUrl", "defaultModel", "enabled", "roleModels", "models") if k in body}
    normalized = {"base_url": fields.get("baseUrl"), "default_model": fields.get("defaultModel"),
                  "role_models": fields.get("roleModels"), "name": fields.get("name"),
                  "enabled": fields.get("enabled"), "models": fields.get("models")}
    provider = svc.update_provider(session, provider_id, **{k: v for k, v in normalized.items() if v is not None})
    if provider is None:
        raise HTTPException(404, "provider not found")
    return svc.to_out(provider)


@router.delete("/{provider_id}", status_code=204)
def delete_provider(provider_id: str, session: Session = Depends(get_db)) -> None:
    svc.delete_provider(session, provider_id)


@router.post("/{provider_id}/test")
async def test_provider(provider_id: str, session: Session = Depends(get_db)) -> dict:
    provider = svc.get_provider(session, provider_id)
    if provider is None:
        raise HTTPException(404, "provider not found")
    try:
        return await provider_from_profile(provider).test_connection()
    except ProviderError as exc:
        return {"ok": False, "error": exc.message, "category": exc.category}


@router.get("/{provider_id}/models")
async def list_models(provider_id: str, session: Session = Depends(get_db)) -> dict:
    provider = svc.get_provider(session, provider_id)
    if provider is None:
        raise HTTPException(404, "provider not found")
    try:
        return {"models": await provider_from_profile(provider).list_models()}
    except ProviderError as exc:
        return {"models": [], "error": exc.message}
