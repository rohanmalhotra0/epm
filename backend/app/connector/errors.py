"""Normalised connector error categories (spec section 40)."""

from __future__ import annotations

from enum import Enum

from ..security.redaction import redact_text


class ErrorCategory(str, Enum):
    authentication = "authentication"
    authorization = "authorization"
    connectivity = "connectivity"
    timeout = "timeout"
    rest_api = "restApi"
    epm_automate = "epmAutomate"
    context = "context"
    member_resolution = "memberResolution"
    form_validation = "formValidation"
    rule_validation = "ruleValidation"
    artifact_generation = "artifactGeneration"
    package_generation = "packageGeneration"
    upload = "upload"
    import_ = "import"
    job_polling = "jobPolling"
    verification = "verification"
    ai_provider = "aiProvider"
    filesystem = "filesystem"
    database = "database"
    security = "security"
    invalid_argument = "invalidArgument"
    not_supported = "notSupported"


class ConnectorError(Exception):
    """A user-safe, redacted, categorised connector failure."""

    def __init__(
        self,
        category: ErrorCategory,
        message: str,
        *,
        likely_cause: str | None = None,
        suggested_action: str | None = None,
        technical_detail: str | None = None,
    ) -> None:
        self.category = category
        self.message = redact_text(message)
        self.likely_cause = redact_text(likely_cause) if likely_cause else None
        self.suggested_action = suggested_action
        self.technical_detail = redact_text(technical_detail) if technical_detail else None
        super().__init__(self.message)

    def to_dict(self) -> dict:
        return {
            "category": self.category.value,
            "message": self.message,
            "likelyCause": self.likely_cause,
            "suggestedAction": self.suggested_action,
            "technicalDetail": self.technical_detail,
        }


class InvalidArgument(ConnectorError):
    def __init__(self, message: str, *, suggested_action: str | None = None) -> None:
        super().__init__(ErrorCategory.invalid_argument, message, suggested_action=suggested_action)
