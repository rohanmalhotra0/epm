"""Impact analysis: where is a member/dimension referenced across saved specs?

Identifier-first, like the rest of the app: the query matches stored string
values exactly (case-insensitive), never fuzzily. The scan walks the stored
spec JSON generically, so forms (``formSpec``), rules (``ruleSpec``) and
reports (``reportSpec``) are all covered without per-schema code, and location
strings are human-readable JSON-path-ish pointers into the camelCase payload
(e.g. ``rows[0].selection.member``).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..db.models import Artifact
from ..schemas.api import ImpactAnalysisOut, ImpactReferenceOut

# Artifact kinds that store a structured specification payload worth scanning.
SPEC_KINDS = ("formSpec", "ruleSpec", "reportSpec")

# Metadata-ish keys that never hold member/dimension identifiers.
_SKIP_KEYS = {"schemaVersion", "contextVersion", "generatedAt", "conversationId", "messageId"}


def _walk(node: object, path: str, query_lower: str, hits: list[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _SKIP_KEYS:
                continue
            _walk(value, f"{path}.{key}" if path else key, query_lower, hits)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            _walk(value, f"{path}[{i}]", query_lower, hits)
    elif isinstance(node, str) and node.lower() == query_lower:
        hits.append(path)


def find_references(session: Session, project_id: str, member: str) -> ImpactAnalysisOut:
    query = member.strip()
    if not query:
        raise ValueError("query member name must not be empty")
    query_lower = query.lower()

    references: list[ImpactReferenceOut] = []
    artifacts = (
        session.query(Artifact)
        .filter(Artifact.project_id == project_id, Artifact.kind.in_(SPEC_KINDS))
        .order_by(Artifact.created_at.asc(), Artifact.id.asc())
        .all()
    )
    for artifact in artifacts:
        if not isinstance(artifact.payload, dict):
            continue
        hits: list[str] = []
        _walk(artifact.payload, "", query_lower, hits)
        if hits:
            references.append(
                ImpactReferenceOut(
                    artifact_id=artifact.id,
                    artifact_type=artifact.kind,
                    artifact_name=artifact.name,
                    locations=hits,
                )
            )
    return ImpactAnalysisOut(query=query, references=references)
