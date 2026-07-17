"""Cube Architecture & Dimensionality Visualizer (spec 4B)."""

from __future__ import annotations

from .service import (
    classify_dimension,
    compare_cubes,
    cross_dimensional_size,
    explain_cell_intersection,
    form_coverage,
    get_cube_architecture,
    inspect_dimension_hierarchy,
    validate_dimension_coverage,
)

__all__ = [
    "get_cube_architecture",
    "form_coverage",
    "validate_dimension_coverage",
    "explain_cell_intersection",
    "compare_cubes",
    "cross_dimensional_size",
    "inspect_dimension_hierarchy",
    "classify_dimension",
]
