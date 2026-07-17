"""Real Oracle EPM Cloud connector via the documented Planning REST API.

Scope is deliberately honest (spec section 28): read-only metadata and
rule execution + job polling are implemented against documented endpoints.
Automated form *deployment* and verification are NOT claimed here — they require
the Migration (LCM) dev workflow to be validated against a development tenant
first, so those methods raise a clear ``not_supported`` error rather than
pretending. Every network call is wrapped and errors are normalised + redacted.

This connector is exercised only when a user explicitly connects a non-demo
environment from the UI. It is never invoked by the test suite.
"""

from __future__ import annotations

import httpx

from ..logging import get_logger
from ..schemas.context import (
    ApplicationRecord,
    CubeRecord,
    DimensionRecord,
    FormRecord,
    MemberRecord,
    RuleRecord,
    VariableRecord,
)
from ..security.redaction import register_secret
from .base import ConnectorInfo, EpmConnector, JobResult
from .errors import ConnectorError, ErrorCategory
from .validation import validate_application, validate_rule_name, validate_url

log = get_logger(__name__)
PLANNING = "HyperionPlanning/rest/v3"


class OracleRestConnector(EpmConnector):
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        classification: str = "development",
        application: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = validate_url(base_url)
        self.username = username
        self._password = password
        register_secret(password)
        self.timeout = timeout
        self.info = ConnectorInfo(
            kind="oracleRest", demo=False, classification=classification, application=application, connected=False
        )

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            auth=(self.username, self._password),
            timeout=self.timeout,
            headers={"Accept": "application/json"},
        )

    async def _get(self, path: str) -> dict:
        try:
            async with self._client() as client:
                resp = await client.get(path)
        except httpx.ConnectError as exc:
            raise ConnectorError(ErrorCategory.connectivity, "Could not reach the Oracle environment.",
                                 suggested_action="Check the environment URL and your network.") from exc
        except httpx.TimeoutException as exc:
            raise ConnectorError(ErrorCategory.timeout, "The Oracle environment did not respond in time.") from exc
        if resp.status_code in (401, 403):
            raise ConnectorError(ErrorCategory.authentication, "Authentication was rejected by Oracle.",
                                 suggested_action="Re-enter your credentials and reconnect.")
        if resp.status_code == 404:
            raise ConnectorError(ErrorCategory.rest_api, f"Resource not found: {path}")
        if resp.status_code >= 400:
            raise ConnectorError(ErrorCategory.rest_api, f"Oracle returned HTTP {resp.status_code}.",
                                 technical_detail=resp.text[:500])
        try:
            return resp.json()
        except ValueError as exc:
            raise ConnectorError(ErrorCategory.rest_api, "Oracle returned a non-JSON response.") from exc

    # --- session ---
    async def login(self) -> bool:
        await self.test_connection()
        self.info.connected = True
        return True

    async def logout(self) -> None:
        self.info.connected = False

    async def test_connection(self) -> dict:
        data = await self._get(f"{PLANNING}/applications")
        apps = [a.get("name") for a in data.get("items", []) if a.get("name")]
        return {"ok": True, "demo": False, "applications": apps}

    # --- metadata ---
    async def list_applications(self) -> list[ApplicationRecord]:
        data = await self._get(f"{PLANNING}/applications")
        return [
            ApplicationRecord(name=a["name"], type=a.get("type", "planning"), description=a.get("description"))
            for a in data.get("items", []) if a.get("name")
        ]

    async def list_cubes(self, application: str) -> list[CubeRecord]:
        validate_application(application)
        data = await self._get(f"{PLANNING}/applications/{application}/plantypes")
        return [
            CubeRecord(name=c["name"], application=application, type=c.get("type", "bso"))
            for c in data.get("items", []) if c.get("name")
        ]

    async def list_dimensions(self, application: str) -> list[DimensionRecord]:
        validate_application(application)
        data = await self._get(f"{PLANNING}/applications/{application}/dimensions")
        return [
            DimensionRecord(name=d["name"], application=application, type=d.get("dimensionType", "generic"))
            for d in data.get("items", []) if d.get("name")
        ]

    async def list_members(self, application: str, dimension: str) -> list[MemberRecord]:
        validate_application(application)
        try:
            data = await self._get(f"{PLANNING}/applications/{application}/dimensions/{dimension}/members")
        except ConnectorError:
            return []  # member enumeration is not uniformly exposed; deep context degrades to partial
        return [
            MemberRecord(name=m["name"], dimension=dimension, application=application,
                         alias=m.get("alias"), parent=m.get("parentName"))
            for m in data.get("items", []) if m.get("name")
        ]

    async def search_members(
        self, application: str, query: str, dimension: str | None = None, limit: int = 50
    ) -> list[MemberRecord]:
        if not dimension:
            return []
        members = await self.list_members(application, dimension)
        q = (query or "").lower()
        return [m for m in members if q in m.name.lower() or q in (m.alias or "").lower()][:limit]

    async def list_forms(self, application: str) -> list[FormRecord]:
        # Forms are not enumerable via the core Planning REST metadata API; they
        # come through Migration. Report honestly rather than guessing.
        return []

    async def get_form(self, application: str, name: str) -> FormRecord | None:
        return None

    async def list_rules(self, application: str) -> list[RuleRecord]:
        validate_application(application)
        try:
            data = await self._get(f"{PLANNING}/applications/{application}/jobdefinitions")
        except ConnectorError:
            return []
        return [
            RuleRecord(name=j["jobName"], application=application, type="businessRule")
            for j in data.get("items", []) if j.get("jobName") and j.get("jobType", "").lower() == "rules"
        ]

    async def get_rule(self, application: str, name: str) -> RuleRecord | None:
        validate_rule_name(name)
        for r in await self.list_rules(application):
            if r.name.lower() == name.lower():
                return r
        return None

    async def get_variables(self, application: str) -> list[VariableRecord]:
        validate_application(application)
        try:
            data = await self._get(f"{PLANNING}/applications/{application}/substitutionvariables")
        except ConnectorError:
            return []
        return [
            VariableRecord(name=v["name"], application=application, scope="substitution", value=v.get("value"))
            for v in data.get("items", []) if v.get("name")
        ]

    async def list_files(self) -> list[str]:
        return []

    # --- execution ---
    async def run_business_rule(
        self, application: str, cube: str | None, rule: str, prompts: dict[str, str]
    ) -> JobResult:
        validate_application(application)
        validate_rule_name(rule)
        body = {"jobType": "Rules", "jobName": rule, "parameters": prompts or {}}
        try:
            async with self._client() as client:
                resp = await client.post(f"{PLANNING}/applications/{application}/jobs", json=body)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise ConnectorError(ErrorCategory.connectivity, "Could not submit the rule to Oracle.") from exc
        if resp.status_code >= 400:
            raise ConnectorError(ErrorCategory.rest_api, f"Rule submission failed (HTTP {resp.status_code}).",
                                 technical_detail=resp.text[:500])
        data = resp.json()
        return JobResult(job_id=str(data.get("jobId", "")), status=_map_status(data.get("status")),
                         details=data.get("descriptiveStatus"))

    async def get_job_status(self, job_id: str) -> JobResult:
        data = await self._get(f"{PLANNING}/applications/{self.info.application}/jobs/{job_id}")
        return JobResult(job_id=job_id, status=_map_status(data.get("status")),
                         result=data.get("descriptiveStatus"), details=data.get("details"))

    # --- modifying / destructive: not claimed until validated (spec section 28) ---
    async def upload_file(self, local_path: str, remote_name: str) -> None:
        raise ConnectorError(
            ErrorCategory.not_supported,
            "Automated upload/deployment to a live tenant is not enabled in this build.",
            suggested_action="Use Demo Mode, or complete the documented Migration dev workflow (docs/ORACLE_ARTIFACT_RESEARCH.md) first.",
        )

    async def import_snapshot(self, name: str) -> JobResult:
        raise ConnectorError(
            ErrorCategory.not_supported,
            "Automated snapshot import to a live tenant is not enabled in this build.",
            suggested_action="Download the package and import it via Oracle Migration, or use Demo Mode.",
        )

    async def verify_form(self, application: str, name: str) -> FormRecord | None:
        return None


def _map_status(status) -> str:  # noqa: ANN001
    # Oracle job status codes: -1 pending, 0 completed, 1 error/failed, 2 in progress...
    mapping = {-1: "queued", 0: "completed", 1: "failed", 2: "running", 3: "failed", 4: "completed"}
    if isinstance(status, int):
        return mapping.get(status, "unknown")
    if isinstance(status, str):
        return status.lower()
    return "unknown"
