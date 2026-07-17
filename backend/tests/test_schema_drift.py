"""Fail if the committed frontend schema files drift from the Pydantic source.

This enforces spec section 3: the frontend must not maintain a second,
independent schema. Regenerate with `python -m scripts.export_schema`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.codegen import generate_all

OUT_DIR = Path(__file__).resolve().parents[2] / "frontend" / "src" / "schemas"


@pytest.mark.parametrize("filename", ["schemas.json", "types.ts", "zod.ts"])
def test_generated_schema_in_sync(filename: str) -> None:
    generated = generate_all()[filename]
    committed_path = OUT_DIR / filename
    assert committed_path.exists(), f"missing generated file {committed_path}"
    committed = committed_path.read_text(encoding="utf-8")
    assert committed == generated, (
        f"{filename} is out of sync with the Pydantic models. "
        f"Run `python -m scripts.export_schema` from backend/ and commit the result."
    )
