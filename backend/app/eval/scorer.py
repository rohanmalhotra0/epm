"""Grade a produced FormSpecification against a lightweight expectation.

An ``Expect`` describes only what a given utterance *should* pin down — a cube, a
row selection, a hidden member — not a whole form. Each populated expectation
field expands into one or more atomic :class:`Check` s. A case's score is
``passed / total`` over its checks, so a spec that gets the cube and rows right
but misses the scenario earns partial credit instead of a flat fail. Aggregating
those checks is what turns the corpus into a coverage percentage.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..artifacts.metadata import TenantMetadata
from ..artifacts.validation import validate_form
from ..schemas.form_spec import AxisMember, FormSpecification


@dataclass
class AxisExpect:
    """Expected placement of one dimension on an axis (any field may be omitted)."""

    dimension: str
    type: str | None = None
    member: str | None = None
    start: str | None = None
    end: str | None = None
    members: list[str] | None = None


@dataclass
class Expect:
    """What an utterance should produce. Every field is optional; only the
    populated ones are scored, so a case asserts exactly what it cares about."""

    cube: str | None = None
    rows: list[AxisExpect] | None = None
    columns: list[AxisExpect] | None = None
    pov: dict[str, str] | None = None  # dimension -> member
    pages: dict[str, str] | None = None  # dimension -> member
    use_aliases: bool | None = None
    read_only: bool | None = None
    hidden_members: list[str] | None = None  # all must be hidden
    rules: list[str] | None = None  # all must be associated
    valid: bool | None = None  # validate_form(...).valid


@dataclass
class Check:
    """One atomic pass/fail assertion, kept with its values for reporting."""

    name: str
    ok: bool
    expected: object
    actual: object

    @property
    def kind(self) -> str:
        """Coarse bucket (``rows.type``, ``pov``, ``display`` …) for the
        per-check-type breakdown in the report."""
        head = self.name.split("[")[0]
        return head


def _axis_member(spec_axis: list[AxisMember], dimension: str) -> AxisMember | None:
    for am in spec_axis:
        if am.dimension.lower() == dimension.lower():
            return am
    return None


def _check_axis(prefix: str, spec_axis: list[AxisMember], expected: list[AxisExpect]) -> list[Check]:
    checks: list[Check] = []
    for ax in expected:
        am = _axis_member(spec_axis, ax.dimension)
        # dimension must be present on the axis at all
        checks.append(Check(f"{prefix}.dimension", am is not None, ax.dimension,
                            am.dimension if am else None))
        if am is None:
            # remaining sub-checks can't pass without the dimension present
            if ax.type is not None:
                checks.append(Check(f"{prefix}.type", False, ax.type, None))
            if ax.member is not None:
                checks.append(Check(f"{prefix}.member", False, ax.member, None))
            continue
        sel = am.selection
        if ax.type is not None:
            checks.append(Check(f"{prefix}.type", sel.type == ax.type, ax.type, sel.type))
        if ax.member is not None:
            checks.append(Check(f"{prefix}.member",
                                (sel.member or "").lower() == ax.member.lower(),
                                ax.member, sel.member))
        if ax.start is not None:
            checks.append(Check(f"{prefix}.start", sel.start == ax.start, ax.start, sel.start))
        if ax.end is not None:
            checks.append(Check(f"{prefix}.end", sel.end == ax.end, ax.end, sel.end))
        if ax.members is not None:
            actual = [m.lower() for m in (sel.members or [])]
            want = [m.lower() for m in ax.members]
            checks.append(Check(f"{prefix}.members", actual == want, ax.members, sel.members))
    return checks


def _check_pov(prefix: str, spec_axis: list[AxisMember], expected: dict[str, str]) -> list[Check]:
    checks: list[Check] = []
    for dimension, member in expected.items():
        am = _axis_member(spec_axis, dimension)
        actual = (am.selection.member if am else None) or (am.selection.variable if am else None)
        ok = am is not None and (actual or "").lower() == member.lower()
        checks.append(Check(f"{prefix}.{dimension}", ok, member, actual))
    return checks


def score_spec(spec: FormSpecification, expect: Expect, md: TenantMetadata) -> list[Check]:
    """Expand a populated ``Expect`` into atomic checks against ``spec``."""
    checks: list[Check] = []

    if expect.cube is not None:
        checks.append(Check("cube", spec.cube == expect.cube, expect.cube, spec.cube))

    if expect.rows is not None:
        checks += _check_axis("rows", spec.rows, expect.rows)
    if expect.columns is not None:
        checks += _check_axis("columns", spec.columns, expect.columns)
    if expect.pov is not None:
        checks += _check_pov("pov", spec.pov, expect.pov)
    if expect.pages is not None:
        checks += _check_pov("pages", spec.pages, expect.pages)

    if expect.use_aliases is not None:
        checks.append(Check("display.useAliases", spec.display.use_aliases == expect.use_aliases,
                            expect.use_aliases, spec.display.use_aliases))
    if expect.read_only is not None:
        checks.append(Check("display.readOnly", spec.display.read_only == expect.read_only,
                            expect.read_only, spec.display.read_only))
    if expect.hidden_members is not None:
        hidden = {h.lower() for h in spec.display.hidden_members}
        for want in expect.hidden_members:
            checks.append(Check("display.hidden", want.lower() in hidden, want,
                                spec.display.hidden_members))

    if expect.rules is not None:
        associated = {a.rule_name.lower() for a in spec.business_rule_associations}
        for want in expect.rules:
            checks.append(Check("rules", want.lower() in associated, want,
                                sorted(associated)))

    if expect.valid is not None:
        actual_valid = validate_form(spec, md).valid
        checks.append(Check("valid", actual_valid == expect.valid, expect.valid, actual_valid))

    return checks


@dataclass
class ScoredCase:
    """A case's checks plus its rolled-up score."""

    id: str
    kind: str  # intent | build | edit
    utterance: str
    checks: list[Check] = field(default_factory=list)
    error: str | None = None
    tags: tuple[str, ...] = ()

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.ok)

    @property
    def total(self) -> int:
        return len(self.checks)

    @property
    def score(self) -> float:
        return 1.0 if self.total == 0 else self.passed / self.total

    @property
    def exact(self) -> bool:
        """True only if every check passed and nothing errored."""
        return self.error is None and self.total > 0 and self.passed == self.total

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.ok]
