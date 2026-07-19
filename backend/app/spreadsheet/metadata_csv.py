"""Deterministic Oracle Planning metadata-import CSV rendering.

Same hierarchy in → byte-identical CSV out (fixed column set, stable member
order, ``\n`` line endings). Saved through the artifacts service like every
other generated artifact (kind ``metadataCsv``, inline content + checksum).
"""

from __future__ import annotations

import csv
import hashlib
import io

from sqlalchemy.orm import Session

from ..db.models import Artifact
from ..services import artifacts as artifacts_svc
from .models import HierarchyParse

RENDERER_VERSION = "1.0.0"
DEFAULT_STORAGE = "Store"


def render_metadata_csv(hierarchy: HierarchyParse, dimension_name: str) -> str:
    """Render an Oracle Planning metadata-import CSV for one dimension.

    Header: ``<Dimension>, Parent, Alias: Default, Data Storage``. Root members
    are parented to the dimension itself (Planning convention). Members are
    emitted in the deterministic order produced by the hierarchy parse.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow([dimension_name, "Parent", "Alias: Default", "Data Storage"])
    for member in hierarchy.members:
        writer.writerow([
            member.name,
            member.parent or dimension_name,
            member.alias or "",
            member.storage or DEFAULT_STORAGE,
        ])
    return buffer.getvalue()


def save_metadata_artifact(
    session: Session,
    project_id: str,
    hierarchy: HierarchyParse,
    dimension_name: str,
) -> Artifact:
    content = render_metadata_csv(hierarchy, dimension_name)
    checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return artifacts_svc.save_artifact(
        session,
        project_id,
        kind="metadataCsv",
        name=f"{dimension_name}_metadata.csv",
        content=content,
        checksum=checksum,
        metadata={
            "dimension": dimension_name,
            "memberCount": len(hierarchy.members),
            "rootCount": hierarchy.root_count,
            "rendererVersion": RENDERER_VERSION,
        },
    )
