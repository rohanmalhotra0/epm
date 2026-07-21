"""Deterministic rule validation layers (spec section 30) -> ValidationReport.

Symmetric to :mod:`app.artifacts.validation` for forms: every check here is
deterministic and grounded in the loaded tenant metadata. This validator
never claims the drafted script is compile-correct — only the *specification*
is checked (its cube, runtime-prompt dimensions, referenced dimensions /
variables / members), plus honest calc-script token sanity. Members are only
ever checked from ``spec.referenced_members`` (the deterministic NLU output),
never parsed out of the free-text script body.
"""

from __future__ import annotations

import re

from ..agent.rule_nlu import _CALC_SCRIPT_RE  # noqa: F401 — reuse the calc vocabulary
from ..connector.validation import _IDENTIFIER_RE
from ..schemas.common import Severity
from ..schemas.rule_spec import RuleSpecification, RuleType
from ..schemas.validation import ValidationIssue, ValidationLayer, ValidationReport
from ..security.redaction import looks_like_secret
from .metadata import TenantMetadata

# Standalone FIX / ENDFIX tokens — the word boundary keeps FIX inside ENDFIX
# from being double-counted (the 'D' before 'F' is a word character).
_FIX_RE = re.compile(r"\bFIX\b", re.I)
_ENDFIX_RE = re.compile(r"\bENDFIX\b", re.I)


def _issue(layer, severity, code, message, path=None, fix=None, candidates=None) -> ValidationIssue:
    return ValidationIssue(
        layer=layer, severity=severity, code=code, message=message,
        path=path, suggested_fix=fix, candidates=candidates or [],
    )


def validate_rule(spec: RuleSpecification, md: TenantMetadata, script: str | None = None) -> ValidationReport:
    """Deterministic validation of a drafted :class:`RuleSpecification`.

    Mirrors :func:`app.artifacts.validation.validate_form`. Never asserts the
    generated script compiles — the calc-script check is a token-balance
    *warning* only.
    """
    report = ValidationReport(artifact_name=spec.name)

    # --- application layer ---
    if md.application and spec.application != md.application:
        report.add(_issue(ValidationLayer.application, Severity.error, "APP_MISMATCH",
                          f"Rule application '{spec.application}' does not match the loaded context "
                          f"application '{md.application}'.", path="application",
                          fix="Rebuild or switch context to the correct application."))
    if not md.has_cube(spec.cube):
        report.add(_issue(ValidationLayer.application, Severity.error, "CUBE_NOT_FOUND",
                          f"Cube '{spec.cube}' does not exist in {spec.application}.", path="cube",
                          candidates=sorted(md.cubes)))

    # --- runtime-prompt layer: each prompt's bound dimension must exist / fit ---
    for idx, prompt in enumerate(spec.runtime_prompts):
        dim = prompt.dimension
        if not dim:
            continue
        path = f"runtimePrompts[{idx}].dimension"
        if not md.has_dimension(dim):
            report.add(_issue(ValidationLayer.runtime_prompt, Severity.error, "DIM_NOT_FOUND",
                              f"Runtime prompt '{prompt.name}' references dimension '{dim}', "
                              "which does not exist.", path=path, candidates=sorted(md.dimensions)))
            continue
        if md.has_cube(spec.cube) and not md.dimension_in_cube(dim, spec.cube):
            report.add(_issue(ValidationLayer.runtime_prompt, Severity.error, "DIM_NOT_IN_CUBE",
                              f"Runtime prompt '{prompt.name}' dimension '{dim}' is not valid for "
                              f"cube '{spec.cube}'.", path=path))

    # --- axis layer: referenced dimensions must exist / fit the cube ---
    for idx, dim in enumerate(spec.referenced_dimensions):
        path = f"referencedDimensions[{idx}]"
        if not md.has_dimension(dim):
            report.add(_issue(ValidationLayer.axis, Severity.error, "DIM_NOT_FOUND",
                              f"Referenced dimension '{dim}' does not exist.", path=path,
                              candidates=sorted(md.dimensions)))
            continue
        if md.has_cube(spec.cube) and not md.dimension_in_cube(dim, spec.cube):
            report.add(_issue(ValidationLayer.axis, Severity.warning, "DIM_NOT_IN_CUBE",
                              f"Referenced dimension '{dim}' is not valid for cube '{spec.cube}'.",
                              path=path))

    # --- selection layer: referenced variables must exist ---
    for idx, var_name in enumerate(spec.referenced_variables):
        if md.get_variable(var_name) is None:
            report.add(_issue(ValidationLayer.selection, Severity.error, "VAR_NOT_FOUND",
                              f"Referenced variable '{var_name}' does not exist.",
                              path=f"referencedVariables[{idx}]"))

    # --- selection layer: referenced members (best-effort, warning only) ---
    # Only spec.referenced_members are checked — never members parsed from the
    # free-text body. Scan the referenced dimensions; unresolvable in all of
    # them is a warning (the member might live on a dimension we can't pin), not
    # a blocking error.
    check_dims = [d for d in spec.referenced_dimensions if md.has_dimension(d)]
    if check_dims:
        for idx, member in enumerate(spec.referenced_members):
            if not any(md.get_member(d, member) is not None for d in check_dims):
                report.add(_issue(ValidationLayer.selection, Severity.warning, "MEMBER_NOT_FOUND",
                                  f"Referenced member '{member}' was not found on any referenced "
                                  f"dimension ({', '.join(check_dims)}).",
                                  path=f"referencedMembers[{idx}]",
                                  fix="Confirm the member name and its dimension."))

    # --- script layer: a rule with no script body at all is empty ---
    body = (script if script is not None else spec.source) or ""
    if not body.strip():
        report.add(_issue(ValidationLayer.script, Severity.error, "EMPTY_SCRIPT",
                          "The rule has no script body — there is nothing to save or import.",
                          path="source", fix="Draft the calc/Groovy script before saving."))

    # --- script layer: calc-script FIX/ENDFIX balance (WARNING — never a
    # compile-correctness claim) ---
    if spec.type == RuleType.calc_script and body.strip():
        fixes = len(_FIX_RE.findall(body))
        endfixes = len(_ENDFIX_RE.findall(body))
        if fixes != endfixes:
            report.add(_issue(ValidationLayer.script, Severity.warning, "UNBALANCED_FIX",
                              f"The calc script has {fixes} FIX and {endfixes} ENDFIX token(s); "
                              "they should be balanced. This is a surface check, not a compile.",
                              path="source",
                              fix="Pair every FIX with an ENDFIX before importing."))

    # --- security layer ---
    if looks_like_secret(spec.name) or (spec.purpose and looks_like_secret(spec.purpose)):
        report.add(_issue(ValidationLayer.security, Severity.error, "SECRET_IN_ARTIFACT",
                          "The rule name or purpose appears to contain a secret. It was blocked.",
                          fix="Remove the credential from the rule metadata."))

    # --- deployment layer ---
    if not _IDENTIFIER_RE.match(spec.name):
        report.add(_issue(ValidationLayer.deployment, Severity.error, "BAD_NAME",
                          f"Rule name '{spec.name}' is not a valid artifact name.", path="name"))

    return report
