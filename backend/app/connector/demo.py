"""Demo connector (spec section 42): the full connector boundary backed by local
fixtures. No Oracle tenant is ever contacted; deployments are simulated and
clearly labelled. Verification checks an in-process registry of demo-created
artifacts so the create -> verify loop is faithful."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..schemas.context import (
    ApplicationRecord,
    CubeRecord,
    DimensionRecord,
    FormRecord,
    MemberRecord,
    RuleRecord,
    VariableRecord,
)
from .base import ConnectorInfo, EpmConnector, JobResult
from .errors import ConnectorError, ErrorCategory
from .validation import validate_application, validate_member, validate_rule_name

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "mcw"

# In-process demo state: application -> {"forms": {name: dict}}. Lets the
# create -> verify loop succeed within a running session.
_demo_state: dict[str, dict] = {}
_job_counter = {"n": 1000}


@lru_cache
def _load(name: str) -> list | dict:
    path = FIXTURES_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def register_deployed_form(application: str, form: dict) -> None:
    _demo_state.setdefault(application, {}).setdefault("forms", {})[form["name"]] = form


def reset_demo_state() -> None:
    _demo_state.clear()


class DemoConnector(EpmConnector):
    def __init__(self, classification: str = "development", application: str = "MCWPCF") -> None:
        self.info = ConnectorInfo(
            kind="demo", demo=True, classification=classification, application=application, connected=True
        )

    # --- session ---
    async def login(self) -> bool:
        self.info.connected = True
        return True

    async def logout(self) -> None:
        self.info.connected = False

    async def test_connection(self) -> dict:
        return {"ok": True, "demo": True, "application": self.info.application,
                "message": "Demo environment — no Oracle tenant is contacted."}

    # --- metadata ---
    async def list_applications(self) -> list[ApplicationRecord]:
        return [ApplicationRecord.model_validate(a) for a in _load("applications.json")]

    async def list_cubes(self, application: str) -> list[CubeRecord]:
        validate_application(application)
        dims = _load("dimensions.json")
        cubes = []
        for c in _load("cubes.json"):
            cube_dims = [d["name"] for d in dims if c["name"] in d.get("cubes", [])]
            cubes.append(CubeRecord.model_validate({**c, "dimensions": cube_dims}))
        return cubes

    async def list_dimensions(self, application: str) -> list[DimensionRecord]:
        validate_application(application)
        return [DimensionRecord.model_validate(d) for d in _load("dimensions.json")]

    async def list_members(self, application: str, dimension: str) -> list[MemberRecord]:
        validate_application(application)
        return [
            MemberRecord.model_validate(m)
            for m in _load("members.json")
            if m["dimension"].lower() == dimension.lower()
        ]

    async def search_members(
        self, application: str, query: str, dimension: str | None = None, limit: int = 50
    ) -> list[MemberRecord]:
        validate_application(application)
        q = (query or "").strip().lower()
        out: list[MemberRecord] = []
        for m in _load("members.json"):
            if dimension and m["dimension"].lower() != dimension.lower():
                continue
            name = m["name"].lower()
            alias = (m.get("alias") or "").lower()
            if not q or q in name or q in alias or name.startswith(q):
                out.append(MemberRecord.model_validate(m))
            if len(out) >= limit:
                break
        return out

    async def list_forms(self, application: str) -> list[FormRecord]:
        validate_application(application)
        base = [FormRecord.model_validate(f) for f in _load("forms.json")]
        for form in _demo_state.get(application, {}).get("forms", {}).values():
            base.append(FormRecord.model_validate(form))
        return base

    async def get_form(self, application: str, name: str) -> FormRecord | None:
        for f in await self.list_forms(application):
            if f.name.lower() == name.lower():
                return f
        return None

    @staticmethod
    def _rule_record(r: dict) -> RuleRecord:
        return RuleRecord(
            name=r["name"],
            application=r["application"],
            cube=r.get("cube"),
            type=r.get("type", "businessRule"),
            runtime_prompts=r.get("runtime_prompts", []),
            has_source=r.get("has_source", False),
        )

    async def list_rules(self, application: str) -> list[RuleRecord]:
        validate_application(application)
        return [self._rule_record(r) for r in _load("rules.json")]

    async def get_rule(self, application: str, name: str) -> RuleRecord | None:
        validate_rule_name(name)
        for r in _load("rules.json"):
            if r["name"].lower() == name.lower():
                return self._rule_record(r)
        return None

    def get_rule_raw(self, name: str) -> dict | None:
        for r in _load("rules.json"):
            if r["name"].lower() == name.lower():
                return r
        return None

    async def get_variables(self, application: str) -> list[VariableRecord]:
        validate_application(application)
        return [VariableRecord.model_validate(v) for v in _load("variables.json")]

    async def list_files(self) -> list[str]:
        forms = _demo_state.get(self.info.application or "", {}).get("forms", {})
        return [f"EPM_Wizard_{n}.zip" for n in forms]

    # --- execution ---
    async def run_business_rule(
        self, application: str, cube: str | None, rule: str, prompts: dict[str, str]
    ) -> JobResult:
        validate_application(application)
        validate_rule_name(rule)
        if await self.get_rule(application, rule) is None:
            raise ConnectorError(
                ErrorCategory.rule_validation,
                f"Rule '{rule}' was not found in {application}.",
                suggested_action="Search the available rules and try again.",
            )
        _job_counter["n"] += 1
        return JobResult(
            job_id=f"DEMO-{_job_counter['n']}",
            status="completed",
            result="success",
            details=f"Rule '{rule}' executed in demo mode. No Oracle data was changed.",
        )

    async def get_job_status(self, job_id: str) -> JobResult:
        return JobResult(job_id=job_id, status="completed", result="success",
                         details="Demo job completed.")

    # --- modifying / destructive ---
    async def upload_file(self, local_path: str, remote_name: str) -> None:
        # Demo: nothing leaves the machine.
        return None

    async def import_snapshot(self, name: str) -> JobResult:
        _job_counter["n"] += 1
        return JobResult(job_id=f"DEMO-IMP-{_job_counter['n']}", status="completed", result="success",
                         details="Demo import completed. No Oracle tenant was modified.")

    async def verify_form(self, application: str, name: str) -> FormRecord | None:
        validate_member(name)
        return await self.get_form(application, name)
