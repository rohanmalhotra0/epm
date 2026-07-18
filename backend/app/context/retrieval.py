"""Local metadata retrieval (spec section 19).

Oracle identifiers and hierarchy relationships take priority over any fuzzy
match. Every result carries full provenance (context version, dimension, exact
name, alias, parent, retrieval method, confidence). The assistant never silently
substitutes a similar member — it reports what it matched and how.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db.models import ContextRecord, ContextVersion
from ..schemas.common import Confidence
from ..schemas.context import MemberMatch

# rank order: lower is better
_METHOD_RANK = {"exact": 0, "caseInsensitive": 1, "alias": 2, "prefix": 3, "substring": 4}
_METHOD_CONFIDENCE = {
    "exact": Confidence.exact,
    "caseInsensitive": Confidence.high,
    "alias": Confidence.high,
    "prefix": Confidence.medium,
    "substring": Confidence.low,
}


def _like_pattern(query: str) -> str:
    """Build a case-folded substring LIKE pattern, escaping the LIKE wildcards so a
    query containing '%' or '_' is matched literally instead of as a wildcard."""
    q = query.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{q}%"


def _classify(query: str, name: str, alias: str | None) -> str | None:
    q = query.strip()
    ql = q.lower()
    if name == q:
        return "exact"
    if name.lower() == ql:
        return "caseInsensitive"
    if alias and alias.lower() == ql:
        return "alias"
    if name.lower().startswith(ql) or (alias and alias.lower().startswith(ql)):
        return "prefix"
    if ql in name.lower() or (alias and ql in alias.lower()):
        return "substring"
    return None


def _to_match(query: str, r: ContextRecord, method: str, context_version: str) -> MemberMatch:
    data = r.data or {}
    return MemberMatch(
        query=query,
        member=r.name,
        alias=r.alias,
        dimension=r.dimension or data.get("dimension", ""),
        application=r.application or data.get("application", ""),
        cube=r.cube,
        parent=r.parent,
        source_artifact=data.get("source_artifact"),
        retrieval_method=method,
        confidence=_METHOD_CONFIDENCE[method],
        context_version=context_version,
    )


def search_members(
    session: Session,
    context_version_id: str,
    query: str,
    dimension: str | None = None,
    limit: int = 25,
) -> list[MemberMatch]:
    cv = session.get(ContextVersion, context_version_id)
    version_label = cv.label if cv else context_version_id
    ql = _like_pattern(query)
    q = session.query(ContextRecord).filter_by(context_version_id=context_version_id, kind="member")
    if dimension:
        q = q.filter(func.lower(ContextRecord.dimension) == dimension.lower())
    q = q.filter(func.lower(ContextRecord.search_text).like(ql, escape="\\"))
    candidates = q.limit(max(limit * 5, 100)).all()

    matches: list[MemberMatch] = []
    for r in candidates:
        method = _classify(query, r.name, r.alias)
        if method:
            matches.append(_to_match(query, r, method, version_label))
    matches.sort(key=lambda m: (_METHOD_RANK[m.retrieval_method], len(m.member)))
    return matches[:limit]


def resolve_member(
    session: Session, context_version_id: str, name: str, dimension: str | None = None
) -> MemberMatch | None:
    """Best single match by name or alias (exact preferred). Used when the
    assistant needs to bind a user's words to an exact technical member."""
    results = search_members(session, context_version_id, name, dimension=dimension, limit=5)
    for m in results:
        if m.retrieval_method in ("exact", "caseInsensitive", "alias"):
            return m
    return results[0] if results else None


def search_all(
    session: Session, context_version_id: str, query: str, kinds: list[str] | None = None, limit: int = 25
) -> list[dict]:
    """Cross-kind search (forms, rules, members, ...) for the /search skill."""
    cv = session.get(ContextVersion, context_version_id)
    version_label = cv.label if cv else context_version_id
    ql = _like_pattern(query)
    q = session.query(ContextRecord).filter_by(context_version_id=context_version_id)
    if kinds:
        q = q.filter(ContextRecord.kind.in_(kinds))
    q = q.filter(func.lower(ContextRecord.search_text).like(ql, escape="\\"))
    out = []
    for r in q.limit(limit).all():
        out.append({
            "kind": r.kind, "name": r.name, "dimension": r.dimension, "cube": r.cube,
            "alias": r.alias, "parent": r.parent, "contextVersion": version_label,
        })
    return out
