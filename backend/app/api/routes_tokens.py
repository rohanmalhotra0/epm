"""Personal API token management for the browser-agent extension.

These routes are behind the normal login gate (they use ``get_current_owner``),
so a signed-in user manages their OWN tokens. The plaintext token is returned
exactly once, at creation. Tokens authenticate the autonomous ``/api/ext``
routes — see ``routes_ext`` and ``services/api_tokens``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db.models import ApiToken
from ..schemas.common import CamelModel
from ..services import api_tokens as tokens_svc
from ..services import iso
from .deps import get_current_owner, get_db

router = APIRouter(prefix="/api/ext-tokens", tags=["ext-tokens"])


class TokenCreate(CamelModel):
    name: str | None = None


class TokenOut(CamelModel):
    id: str
    name: str
    prefix: str
    created_at: str
    last_used_at: str | None = None


class TokenCreated(TokenOut):
    # The full secret — returned ONLY here, never again.
    token: str


def _to_out(t: ApiToken) -> TokenOut:
    return TokenOut(
        id=t.id,
        name=t.name,
        prefix=t.prefix,
        created_at=iso(t.created_at),
        last_used_at=iso(t.last_used_at) if t.last_used_at else None,
    )


@router.get("")
def list_tokens(session: Session = Depends(get_db),
                owner: str = Depends(get_current_owner)) -> list[TokenOut]:
    return [_to_out(t) for t in tokens_svc.list_tokens(session, owner)]


@router.post("", status_code=201)
def create_token(body: TokenCreate,
                 session: Session = Depends(get_db),
                 owner: str = Depends(get_current_owner)) -> TokenCreated:
    row, plaintext = tokens_svc.create_token(session, owner, body.name)
    out = _to_out(row)
    return TokenCreated(**out.model_dump(by_alias=False), token=plaintext)


@router.delete("/{token_id}", status_code=204)
def revoke_token(token_id: str,
                 session: Session = Depends(get_db),
                 owner: str = Depends(get_current_owner)) -> None:
    if not tokens_svc.revoke_token(session, owner, token_id):
        raise HTTPException(status_code=404, detail="token not found")
