"""Context engine, retrieval and portable packages (spec sections 16-19)."""

from __future__ import annotations

from .engine import ContextBundle, build_context, diff_contexts, environment_fingerprint
from .package import export_context_package, import_context_package, validate_context_package
from .retrieval import resolve_member, search_all, search_members
from .snapshot import (
    SnapshotBundle,
    SnapshotError,
    analyze_snapshot,
    merge_snapshot_into_context,
    summarize_snapshot,
)

__all__ = [
    "ContextBundle",
    "build_context",
    "diff_contexts",
    "environment_fingerprint",
    "export_context_package",
    "import_context_package",
    "validate_context_package",
    "search_members",
    "resolve_member",
    "search_all",
    "SnapshotBundle",
    "SnapshotError",
    "analyze_snapshot",
    "merge_snapshot_into_context",
    "summarize_snapshot",
]
