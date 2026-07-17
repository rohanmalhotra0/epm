"""Oracle-EPM "smart formatting" — deterministic number formatting + sampling.

Pure functions shared by the report preview builder and renderers. Given a raw
numeric value and a ``SmartFormat`` they produce the display string plus the
colour / weight / negative flags a renderer needs. Sample values are derived from
a stable hash so a report always renders identically (Demo Mode has no live
data).
"""

from __future__ import annotations

import hashlib

from ..schemas.report_preview import ReportCell
from ..schemas.report_spec import Comparator, NegativeStyle, SmartFormat

_COMPARATORS = {
    Comparator.lt: lambda a, b: a < b,
    Comparator.le: lambda a, b: a <= b,
    Comparator.gt: lambda a, b: a > b,
    Comparator.ge: lambda a, b: a >= b,
    Comparator.eq: lambda a, b: a == b,
    Comparator.ne: lambda a, b: a != b,
}


def sample_value(*parts: str) -> float:
    """A stable pseudo-value for an intersection (deterministic across runs).

    Ranges look like plausible financials: mostly positive thousands, with an
    occasional negative to exercise negative styling.
    """
    key = "||".join(parts)
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    n = int.from_bytes(digest[:6], "big")
    magnitude = (n % 900000) + 1000  # 1,000 .. 901,000
    # ~1 in 6 intersections negative
    sign = -1 if (digest[6] % 6 == 0) else 1
    # one decimal of variation
    cents = (digest[7] % 100) / 100.0
    return round(sign * (magnitude + cents), 2)


def _scaled(value: float, scale: int) -> float:
    if scale > 0:
        return value / (10 ** scale)
    return value


def format_number(value: float, fmt: SmartFormat) -> str:
    scaled = _scaled(value, fmt.scale)
    negative = scaled < 0
    magnitude = abs(scaled)
    if fmt.thousands_separator:
        body = f"{magnitude:,.{fmt.decimal_places}f}"
    else:
        body = f"{magnitude:.{fmt.decimal_places}f}"
    body = f"{fmt.prefix}{body}{fmt.suffix}"
    if not negative:
        return body
    style = NegativeStyle(fmt.negative_style)
    if style in (NegativeStyle.parentheses, NegativeStyle.red_parentheses):
        return f"({body})"
    return f"-{body}"


def negative_color(fmt: SmartFormat) -> str | None:
    style = NegativeStyle(fmt.negative_style)
    if style in (NegativeStyle.red, NegativeStyle.red_parentheses):
        return "#da1e28"
    return None


def build_cell(value: float, fmt: SmartFormat, note: str | None = None) -> ReportCell:
    """Apply a SmartFormat (base + conditional rules) to a value -> ReportCell."""
    negative = _scaled(value, fmt.scale) < 0
    color: str | None = negative_color(fmt) if negative else None
    background: str | None = None
    bold = False
    for rule in fmt.conditional_rules:
        cmp = _COMPARATORS.get(Comparator(rule.comparator))
        if cmp and cmp(value, rule.value):
            if rule.color:
                color = rule.color
            if rule.background:
                background = rule.background
            if rule.bold:
                bold = True
    return ReportCell(
        value=value,
        formatted=format_number(value, fmt),
        color=color,
        background=background,
        bold=bold,
        negative=negative,
        note=note,
    )


def merge_format(base: SmartFormat, override: SmartFormat | None) -> SmartFormat:
    """A column/cell override fully replaces the base when present."""
    return override if override is not None else base
