"""Strict argument validation for every value that reaches the runner or REST
API (spec section 14). No value is ever interpolated into a shell — but we still
validate aggressively to reject path traversal, injection and malformed input.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from .errors import InvalidArgument

# Oracle identifiers (members, rules, apps, dimensions) allow letters, digits,
# spaces and a small punctuation set. Deliberately excludes shell metacharacters,
# path separators, quotes and control characters.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9 _\-.,:@#()/&+%']{1,200}$")
_FILENAME_RE = re.compile(r"^[A-Za-z0-9 _\-.]{1,180}$")
_SNAPSHOT_RE = re.compile(r"^[A-Za-z0-9 _\-.]{1,120}$")
_SHELL_META = set(";|&$`<>\n\r\t\0*?!")


def _reject_shell(value: str, field: str) -> None:
    if any(c in _SHELL_META for c in value):
        raise InvalidArgument(f"{field} contains a disallowed character")


def validate_identifier(value: str, field: str = "identifier") -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidArgument(f"{field} must be a non-empty string")
    value = value.strip()
    _reject_shell(value, field)
    if ".." in value:  # no legitimate Oracle identifier contains a parent-traversal
        raise InvalidArgument(f"{field} must not contain '..'")
    if not _IDENTIFIER_RE.match(value):
        raise InvalidArgument(f"{field} '{value[:40]}' is not a valid Oracle identifier")
    return value


def validate_rule_name(value: str) -> str:
    return validate_identifier(value, "rule name")


def validate_application(value: str) -> str:
    return validate_identifier(value, "application")


def validate_member(value: str) -> str:
    return validate_identifier(value, "member")


def validate_prompt_name(value: str) -> str:
    return validate_identifier(value, "runtime prompt name")


def validate_prompt_value(value: str) -> str:
    if not isinstance(value, str):
        raise InvalidArgument("runtime prompt value must be a string")
    if len(value) > 400:
        raise InvalidArgument("runtime prompt value is too long")
    _reject_shell(value, "runtime prompt value")
    return value


def validate_filename(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidArgument("filename must be a non-empty string")
    value = value.strip()
    if "/" in value or "\\" in value or ".." in value:
        raise InvalidArgument("filename must not contain path separators")
    if not _FILENAME_RE.match(value):
        raise InvalidArgument(f"filename '{value[:40]}' is not allowed")
    return value


def validate_snapshot_name(value: str) -> str:
    value = (value or "").strip()
    if not _SNAPSHOT_RE.match(value):
        raise InvalidArgument("snapshot name is not allowed")
    return value


def validate_path_within(base: Path, candidate: Path) -> Path:
    base = base.resolve()
    resolved = (base / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
    if base != resolved and base not in resolved.parents:
        raise InvalidArgument("path escapes the permitted working directory")
    return resolved


def validate_url(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidArgument("environment URL is required")
    parsed = urlparse(value.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise InvalidArgument("environment URL must be a valid http(s) URL")
    return value.strip().rstrip("/")


def validate_timeout(value: int, *, maximum: int = 3600) -> int:
    if not isinstance(value, int) or value <= 0 or value > maximum:
        raise InvalidArgument(f"timeout must be between 1 and {maximum} seconds")
    return value
