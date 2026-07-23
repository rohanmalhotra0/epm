"""Production-safety coverage for ephemeral parallel-agent sessions."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app import main as main_module
from app.agent.team_sessions import (
    TeamSessionCapacityError,
    TeamSessionConflict,
    TeamSessionNotFound,
    TeamSessionOwnerCapacityError,
    TeamSessionRegistry,
    team_sessions,
)
from app.ai.base import (
    AIMessage,
    AIProvider,
    ProviderConfig,
    StreamChunk,
    StreamDone,
)
from app.api import routes_agent
from app.schemas.agent import AgentTeamSessionRequest


class RecordingProvider(AIProvider):
    """Small provider double that can finish immediately or wait on a gate."""

    def __init__(self, *, blocked: bool = False, fail_role: str | None = None) -> None:
        super().__init__(
            ProviderConfig(provider_type="test", default_model="team-test")
        )
        self.calls: list[tuple[list[AIMessage], str | None]] = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        if not blocked:
            self.release.set()
        self.fail_role = fail_role

    async def list_models(self) -> list[str]:
        return ["team-test"]

    async def test_connection(self) -> dict:
        return {"ok": True}

    async def stream(
        self,
        messages: list[AIMessage],
        *,
        system: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        cancel=None,
    ) -> AsyncIterator[StreamChunk]:
        yield StreamDone()

    async def complete(
        self,
        messages: list[AIMessage],
        *,
        system: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> str:
        self.calls.append((list(messages), system))
        self.started.set()
        await self.release.wait()
        role = (system or "").splitlines()[0].partition(":")[2].strip()
        if self.fail_role and role == self.fail_role:
            raise RuntimeError(f"{role} failed deliberately")
        return f"{role} result for {messages[-1].content}"


async def _wait_for_status(
    registry: TeamSessionRegistry,
    session_id: str,
    owner: str,
    expected: str,
) -> None:
    for _ in range(100):
        if registry.get(session_id, owner).status == expected:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(
        f"session {session_id} did not reach {expected}: "
        f"{registry.get(session_id, owner).status}"
    )


async def test_one_provider_call_per_agent_and_outputs_are_role_specific():
    registry = TeamSessionRegistry()
    provider = RecordingProvider()
    created = await registry.start(
        owner="owner-a",
        goal="Validate the Workforce forecast",
        project_id=None,
        agent_count=4,
        provider=provider,
    )

    await _wait_for_status(registry, created.id, "owner-a", "completed")
    finished = registry.get(created.id, "owner-a")

    assert len(provider.calls) == 4
    assert all(call[0][-1].content == created.goal for call in provider.calls)
    assert {agent.status for agent in finished.agents} == {"completed"}
    assert len({agent.output for agent in finished.agents}) == 4
    await registry.shutdown()


async def test_worker_failure_is_isolated_from_the_rest_of_the_team():
    registry = TeamSessionRegistry()
    provider = RecordingProvider(fail_role="Metadata analyst")
    created = await registry.start(
        owner="owner-a",
        goal="Review a planning rule",
        project_id=None,
        agent_count=3,
        provider=provider,
    )

    await _wait_for_status(registry, created.id, "owner-a", "failed")
    finished = registry.get(created.id, "owner-a")

    assert finished.status == "failed"
    assert [agent.status for agent in finished.agents].count("failed") == 1
    assert [agent.status for agent in finished.agents].count("completed") == 2
    assert "remaining workers continued" in next(
        agent.activity for agent in finished.agents if agent.status == "failed"
    )
    await registry.shutdown()


async def test_pause_resume_and_cancel_hold_provider_output_on_the_app_loop():
    registry = TeamSessionRegistry()
    provider = RecordingProvider(blocked=True)
    created = await registry.start(
        owner="owner-a",
        goal="Prepare a validation plan",
        project_id=None,
        agent_count=2,
        provider=provider,
    )
    await provider.started.wait()

    paused = registry.pause(created.id, "owner-a")
    assert paused.status == "paused"
    assert {agent.status for agent in paused.agents} == {"paused"}

    provider.release.set()
    await asyncio.sleep(0.02)
    assert registry.get(created.id, "owner-a").status == "paused"

    resumed = registry.resume(created.id, "owner-a")
    assert resumed.status == "running"
    await _wait_for_status(registry, created.id, "owner-a", "completed")

    with pytest.raises(TeamSessionConflict):
        registry.cancel(created.id, "owner-a")

    blocked_again = RecordingProvider(blocked=True)
    cancellable = await registry.start(
        owner="owner-a",
        goal="Prepare another plan",
        project_id=None,
        agent_count=1,
        provider=blocked_again,
    )
    await blocked_again.started.wait()
    cancelled = registry.cancel(cancellable.id, "owner-a")
    assert cancelled.status == "cancelled"
    assert cancelled.agents[0].status == "cancelled"
    await registry.shutdown()


async def test_owner_isolation_hides_existing_sessions():
    registry = TeamSessionRegistry()
    created = await registry.start(
        owner="owner-a",
        goal="Private task",
        project_id=None,
        agent_count=1,
        provider=RecordingProvider(blocked=True),
    )

    with pytest.raises(TeamSessionNotFound):
        registry.get(created.id, "owner-b")
    with pytest.raises(TeamSessionNotFound):
        registry.pause(created.id, "owner-b")
    with pytest.raises(TeamSessionNotFound):
        registry.cancel(created.id, "owner-b")
    await registry.shutdown()


async def test_global_capacity_rejects_when_no_terminal_slot_can_be_reclaimed():
    registry = TeamSessionRegistry(
        max_sessions=1,
        max_active_sessions_per_owner=10,
        max_active_workers_per_owner=100,
    )
    await registry.start(
        owner="owner-a",
        goal="First task",
        project_id=None,
        agent_count=1,
        provider=RecordingProvider(blocked=True),
    )

    with pytest.raises(TeamSessionCapacityError):
        await registry.start(
            owner="owner-b",
            goal="Second task",
            project_id=None,
            agent_count=1,
            provider=RecordingProvider(blocked=True),
        )
    await registry.shutdown()


async def test_per_owner_session_and_worker_cost_bounds():
    session_limited = TeamSessionRegistry(
        max_sessions=10,
        max_active_sessions_per_owner=1,
        max_active_workers_per_owner=12,
    )
    await session_limited.start(
        owner="owner-a",
        goal="First task",
        project_id=None,
        agent_count=1,
        provider=RecordingProvider(blocked=True),
    )
    with pytest.raises(TeamSessionOwnerCapacityError):
        await session_limited.start(
            owner="owner-a",
            goal="Second task",
            project_id=None,
            agent_count=1,
            provider=RecordingProvider(blocked=True),
        )
    # Capacity is scoped per owner, not global.
    await session_limited.start(
        owner="owner-b",
        goal="Other owner's task",
        project_id=None,
        agent_count=1,
        provider=RecordingProvider(blocked=True),
    )
    await session_limited.shutdown()

    worker_limited = TeamSessionRegistry(
        max_sessions=10,
        max_active_sessions_per_owner=5,
        max_active_workers_per_owner=3,
    )
    await worker_limited.start(
        owner="owner-a",
        goal="Two-worker task",
        project_id=None,
        agent_count=2,
        provider=RecordingProvider(blocked=True),
    )
    with pytest.raises(TeamSessionOwnerCapacityError):
        await worker_limited.start(
            owner="owner-a",
            goal="Another two-worker task",
            project_id=None,
            agent_count=2,
            provider=RecordingProvider(blocked=True),
        )
    await worker_limited.shutdown()


async def test_shutdown_cancels_workers_and_clears_registry():
    registry = TeamSessionRegistry()
    provider = RecordingProvider(blocked=True)
    created = await registry.start(
        owner="owner-a",
        goal="Long-running task",
        project_id=None,
        agent_count=2,
        provider=provider,
    )
    await provider.started.wait()

    await registry.shutdown()

    with pytest.raises(TeamSessionNotFound):
        registry.get(created.id, "owner-a")


async def test_app_lifespan_shuts_down_the_global_registry(monkeypatch):
    settings = SimpleNamespace(
        log_level="INFO",
        log_json=False,
        startup_migrations=False,
        is_sqlite=False,
        app_name="EPM Wizard",
        version="test",
        data_dir="/tmp/epmw-test",
    )
    shutdown = AsyncMock()
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    monkeypatch.setattr(main_module, "configure_logging", lambda *_args: None)
    monkeypatch.setattr(main_module, "initialize", lambda **_kwargs: None)
    monkeypatch.setattr(team_sessions, "shutdown", shutdown)

    async with main_module.lifespan(main_module.app):
        pass

    shutdown.assert_awaited_once_with()


async def test_create_session_project_404_does_not_reveal_ownership(monkeypatch):
    class ProjectLookup:
        def __init__(self, project) -> None:
            self.project = project

        def get(self, _model, _project_id):
            return self.project

    body = AgentTeamSessionRequest(
        goal="Review a planning rule",
        project_id="project-private",
        agent_count=1,
    )

    with pytest.raises(HTTPException) as missing:
        await routes_agent.create_agent_session(
            body,
            session=ProjectLookup(None),
            owner="owner-b",
        )

    def deny_cross_owner(*_args) -> None:
        raise HTTPException(status_code=404, detail="not found")

    monkeypatch.setattr(routes_agent, "authorize_project_id", deny_cross_owner)
    with pytest.raises(HTTPException) as cross_owner:
        await routes_agent.create_agent_session(
            body,
            session=ProjectLookup(object()),
            owner="owner-b",
        )

    assert missing.value.detail == "project not found"
    assert cross_owner.value.detail == "project not found"


def test_lifecycle_routes_are_async_and_blank_goals_are_rejected():
    assert inspect.iscoroutinefunction(routes_agent.pause_agent_session)
    assert inspect.iscoroutinefunction(routes_agent.resume_agent_session)
    assert inspect.iscoroutinefunction(routes_agent.cancel_agent_session)

    with pytest.raises(ValueError):
        AgentTeamSessionRequest(goal="   ", agent_count=1)
