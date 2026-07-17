"""Write the generated frontend schema files from the canonical Pydantic models.

Usage (from backend/):  python -m scripts.export_schema
"""

from __future__ import annotations

from pathlib import Path

from app.codegen import generate_all

OUT_DIR = Path(__file__).resolve().parents[2] / "frontend" / "src" / "schemas"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = generate_all()
    for name, content in files.items():
        path = OUT_DIR / name
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path}  ({len(content):,} bytes)")


if __name__ == "__main__":
    main()
