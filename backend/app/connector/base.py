"""The one authoritative EPM connector boundary (spec section 14).

The language model never calls EPM Automate or Oracle REST directly. Every Oracle
interaction goes through an ``EpmConnector`` implementation via explicit, typed,
classified methods. There is deliberately no generic command endpoint.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel

from ..schemas.context import (
    ApplicationRecord,
    CubeRecord,
    DimensionRecord,
    FormRecord,
    MemberRecord,
    RuleRecord,
    VariableRecord,
)


class JobResult(BaseModel):
    job_id: str
    status: str  # queued | running | completed | failed | cancelled | unknown
    result: str | None = None
    details: str | None = None


class ConnectorInfo(BaseModel):
    kind: str  # demo | oracleRest | epmAutomate
    demo: bool
    classification: str
    application: str | None = None
    connected: bool = False


class EpmConnector(ABC):
    """Abstract connector. Implementations must classify each operation and must
    never expose a generic command surface."""

    info: ConnectorInfo

    # --- session ---
    @abstractmethod
    async def login(self) -> bool: ...

    @abstractmethod
    async def logout(self) -> None: ...

    @abstractmethod
    async def test_connection(self) -> dict: ...

    # --- read-only metadata ---
    @abstractmethod
    async def list_applications(self) -> list[ApplicationRecord]: ...

    @abstractmethod
    async def list_cubes(self, application: str) -> list[CubeRecord]: ...

    @abstractmethod
    async def list_dimensions(self, application: str) -> list[DimensionRecord]: ...

    @abstractmethod
    async def list_members(self, application: str, dimension: str) -> list[MemberRecord]: ...

    @abstractmethod
    async def search_members(
        self, application: str, query: str, dimension: str | None = None, limit: int = 50
    ) -> list[MemberRecord]: ...

    @abstractmethod
    async def list_forms(self, application: str) -> list[FormRecord]: ...

    @abstractmethod
    async def get_form(self, application: str, name: str) -> FormRecord | None: ...

    @abstractmethod
    async def list_rules(self, application: str) -> list[RuleRecord]: ...

    @abstractmethod
    async def get_rule(self, application: str, name: str) -> RuleRecord | None: ...

    @abstractmethod
    async def get_variables(self, application: str) -> list[VariableRecord]: ...

    @abstractmethod
    async def list_files(self) -> list[str]: ...

    # --- execution (approval required upstream) ---
    @abstractmethod
    async def run_business_rule(
        self, application: str, cube: str | None, rule: str, prompts: dict[str, str]
    ) -> JobResult: ...

    @abstractmethod
    async def get_job_status(self, job_id: str) -> JobResult: ...

    # --- modifying / destructive (approval required upstream) ---
    @abstractmethod
    async def upload_file(self, local_path: str, remote_name: str) -> None: ...

    @abstractmethod
    async def import_snapshot(self, name: str) -> JobResult: ...

    @abstractmethod
    async def verify_form(self, application: str, name: str) -> FormRecord | None: ...
