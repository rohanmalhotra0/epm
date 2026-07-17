"""Deterministic form validation layers (spec section 26) -> ValidationReport."""

from __future__ import annotations

from ..connector.validation import _IDENTIFIER_RE
from ..schemas.common import SelectionType, Severity
from ..schemas.form_spec import AxisMember, FormSpecification
from ..schemas.validation import (
    SizeEstimate,
    ValidationIssue,
    ValidationLayer,
    ValidationReport,
)
from ..security.redaction import looks_like_secret
from .metadata import TenantMetadata
from .resolver import ResolutionError, resolve_selection

SIZE_WARN = 250_000


def _issue(layer, severity, code, message, path=None, fix=None, candidates=None) -> ValidationIssue:
    return ValidationIssue(
        layer=layer, severity=severity, code=code, message=message,
        path=path, suggested_fix=fix, candidates=candidates or [],
    )


def validate_form(spec: FormSpecification, md: TenantMetadata) -> ValidationReport:
    report = ValidationReport(artifact_name=spec.name)

    # --- application layer ---
    if md.application and spec.application != md.application:
        report.add(_issue(ValidationLayer.application, Severity.error, "APP_MISMATCH",
                          f"Form application '{spec.application}' does not match the loaded context "
                          f"application '{md.application}'.", path="application",
                          fix="Rebuild or switch context to the correct application."))
    if not md.has_cube(spec.cube):
        report.add(_issue(ValidationLayer.application, Severity.error, "CUBE_NOT_FOUND",
                          f"Cube '{spec.cube}' does not exist in {spec.application}.", path="cube",
                          candidates=sorted(md.cubes)))

    # --- axis + selection layers ---
    placed: set[str] = set()
    for kind, axis in (("pov", spec.pov), ("pages", spec.pages), ("rows", spec.rows), ("columns", spec.columns)):
        for idx, am in enumerate(axis):
            path = f"{kind}[{idx}]"
            placed.add(am.dimension)
            if not md.has_dimension(am.dimension):
                report.add(_issue(ValidationLayer.axis, Severity.error, "DIM_NOT_FOUND",
                                  f"Dimension '{am.dimension}' does not exist.", path=path,
                                  candidates=sorted(md.dimensions)))
                continue
            if md.has_cube(spec.cube) and not md.dimension_in_cube(am.dimension, spec.cube):
                report.add(_issue(ValidationLayer.axis, Severity.error, "DIM_NOT_IN_CUBE",
                                  f"Dimension '{am.dimension}' is not valid for cube '{spec.cube}'.", path=path))
            _validate_selection(md, report, am, path)

    # required-dimension coverage (info/warning, not blocking)
    if md.has_cube(spec.cube):
        missing = [d for d in md.cubes[spec.cube].dimensions if d not in placed]
        if missing:
            report.add(_issue(ValidationLayer.axis, Severity.info, "DIM_DEFAULTED",
                              f"Dimensions not placed on the form will default to a single member: {', '.join(missing)}.",
                              fix="Add them to the POV if a specific member is required."))

    # --- display layer ---
    for hidden in spec.display.hidden_members:
        if not _member_exists_anywhere(md, spec, hidden):
            report.add(_issue(ValidationLayer.display, Severity.warning, "HIDDEN_UNKNOWN",
                              f"Hidden member '{hidden}' was not found on any row/column dimension.",
                              path="display.hiddenMembers"))

    # --- performance layer ---
    size = _estimate_size(spec, md)
    report.size_estimate = size
    if size.total_cells > SIZE_WARN:
        report.add(_issue(ValidationLayer.performance, Severity.warning, "LARGE_FORM",
                          f"This form resolves to about {size.total_cells:,} cells, which may be slow to open.",
                          fix="Add suppression, reduce the member selection, or move a dimension to the POV."))

    # --- security layer ---
    if looks_like_secret(spec.name) or (spec.description and looks_like_secret(spec.description)):
        report.add(_issue(ValidationLayer.security, Severity.error, "SECRET_IN_ARTIFACT",
                          "The form name or description appears to contain a secret. It was blocked.",
                          fix="Remove the credential from the form metadata."))

    # --- deployment layer ---
    if not _IDENTIFIER_RE.match(spec.name):
        report.add(_issue(ValidationLayer.deployment, Severity.error, "BAD_NAME",
                          f"Form name '{spec.name}' is not a valid artifact name.", path="name"))

    return report


def _validate_selection(md: TenantMetadata, report: ValidationReport, am: AxisMember, path: str) -> None:
    sel = am.selection
    t = SelectionType(sel.type)
    # variable/dimension consistency
    if t in (SelectionType.user_variable, SelectionType.substitution_variable):
        var = md.get_variable(sel.variable)
        if var is None:
            report.add(_issue(ValidationLayer.selection, Severity.error, "VAR_NOT_FOUND",
                              f"Variable '{sel.variable}' does not exist.", path=f"{path}.selection"))
            return
        if var.dimension and var.dimension != am.dimension:
            report.add(_issue(ValidationLayer.selection, Severity.warning, "VAR_DIM_MISMATCH",
                              f"Variable '{sel.variable}' belongs to dimension '{var.dimension}', "
                              f"not '{am.dimension}'.", path=f"{path}.selection"))
        return
    if not md.has_dimension(am.dimension):
        return
    try:
        res = resolve_selection(md, am.dimension, sel)
        report.resolved_member_counts[f"{path}:{am.dimension}"] = len(res.members)
        if not res.members:
            report.add(_issue(ValidationLayer.selection, Severity.error, "EMPTY_SELECTION",
                              f"Selection on '{am.dimension}' did not resolve to any members.",
                              path=f"{path}.selection"))
    except ResolutionError as exc:
        report.add(_issue(ValidationLayer.selection, Severity.error, "MEMBER_NOT_FOUND",
                          exc.message, path=f"{path}.selection",
                          fix="Choose one of the matching members below." if exc.candidates else None,
                          candidates=exc.candidates))


def _member_exists_anywhere(md: TenantMetadata, spec: FormSpecification, name: str) -> bool:
    dims = {am.dimension for _, am in spec.all_axis_members()}
    return any(md.get_member(d, name) is not None for d in dims)


def _estimate_size(spec: FormSpecification, md: TenantMetadata) -> SizeEstimate:
    def axis_count(axis: list[AxisMember]) -> int:
        total = 1
        for am in axis:
            try:
                total *= max(1, len(resolve_selection(md, am.dimension, am.selection).members))
            except ResolutionError:
                total *= 1
        return total

    rows = axis_count(spec.rows)
    cols = axis_count(spec.columns)
    pages = axis_count(spec.pages) if spec.pages else 1
    return SizeEstimate(row_combinations=rows, column_combinations=cols,
                        page_combinations=pages, total_cells=rows * cols * pages)
