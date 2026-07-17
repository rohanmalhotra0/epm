"""Deterministic artifact engine (spec sections 4, 27). The LLM never owns the
deployable artifact — this code does."""

from __future__ import annotations

from .metadata import TenantMetadata, build_metadata, build_metadata_from_connector
from .packager import build_form_package, sha256
from .parser import clone_from_reference, parse_definition, parse_xml
from .preview import build_preview
from .renderer import RENDERER_VERSION, render_json, render_markdown, render_xml
from .resolver import Resolution, ResolutionError, resolve_selection
from .validation import validate_form

__all__ = [
    "TenantMetadata",
    "build_metadata",
    "build_metadata_from_connector",
    "resolve_selection",
    "Resolution",
    "ResolutionError",
    "build_preview",
    "validate_form",
    "render_xml",
    "render_json",
    "render_markdown",
    "RENDERER_VERSION",
    "build_form_package",
    "sha256",
    "parse_xml",
    "parse_definition",
    "clone_from_reference",
]
