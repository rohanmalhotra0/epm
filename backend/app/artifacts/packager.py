"""Deterministic import-package construction (spec section 27).

Builds a normalised migration-style bundle as a reproducible ZIP with per-file
SHA-256 checksums and a manifest. Given the same spec + renderer version the ZIP
bytes are byte-identical (fixed entry order, fixed timestamps), enabling the
"re-render without changes / compare packages" workflow.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile

from ..schemas.form_spec import FormSpecification
from .renderer import RENDERER_VERSION, render_json, render_xml

_FIXED_DT = (1980, 1, 1, 0, 0, 0)
PACKAGER_VERSION = "1.0.0"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe(name: str) -> str:
    return "".join(c if (c.isalnum() or c in " _-") else "_" for c in name).strip().replace(" ", "_")


def build_form_package(spec: FormSpecification, generated_at: str | None = None) -> dict:
    """Return {'zip': bytes, 'manifest': dict, 'checksum': str, 'files': {name: text}}."""
    pkg_root = f"EPM_Wizard_{_safe(spec.name)}"
    folder_path = "/".join(_safe(p) for p in spec.folder.split("/") if p)

    form_xml = render_xml(spec)
    form_json = render_json(spec)
    readme = (
        f"EPM Wizard normalised form package\n"
        f"Form: {spec.name}\nApplication: {spec.application}\nCube: {spec.cube}\n"
        f"Folder: {spec.folder}\nRenderer: {RENDERER_VERSION}\n\n"
        f"This bundle is generated deterministically by EPM Wizard. It is NOT a\n"
        f"claim about Oracle's exact Cloud package layout; see docs/ORACLE_ARTIFACT_RESEARCH.md.\n"
    )

    files: dict[str, str] = {
        f"{pkg_root}/resource/Global Artifacts/Data Forms/{folder_path}/{_safe(spec.name)}.xml": form_xml,
        f"{pkg_root}/resource/Global Artifacts/Data Forms/{folder_path}/{_safe(spec.name)}.json": form_json,
        f"{pkg_root}/README.txt": readme,
    }

    checksums = {name: sha256(text.encode("utf-8")) for name, text in sorted(files.items())}
    manifest = {
        "format": "epmwizard-package",
        "packagerVersion": PACKAGER_VERSION,
        "rendererVersion": RENDERER_VERSION,
        "specSchemaVersion": spec.schema_version,
        "artifactType": "planningForm",
        "artifactName": spec.name,
        "application": spec.application,
        "cube": spec.cube,
        "folder": spec.folder,
        "files": sorted(files.keys()),
        "checksums": checksums,
    }
    if generated_at:
        manifest["generatedAt"] = generated_at
    manifest_text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    files[f"{pkg_root}/manifest.json"] = manifest_text

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(files.keys()):
            info = zipfile.ZipInfo(filename=name, date_time=_FIXED_DT)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, files[name])
    zip_bytes = buffer.getvalue()

    return {
        "zip": zip_bytes,
        "manifest": manifest,
        "checksum": sha256(zip_bytes),
        "files": files,
        "pkg_root": pkg_root,
    }
