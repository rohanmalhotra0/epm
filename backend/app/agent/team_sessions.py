"""Ephemeral, owner-scoped parallel-agent sessions.

This is intentionally a sandbox rather than a durable job system: sessions live
in memory, have a small bounded registry, and are removed after a TTL. Workers
only ask the selected AI provider for analysis. They receive no connector,
browser, deployment, or persistence tools, so starting a team cannot write to
EPM or claim to operate a user's screen.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import RLock
from uuid import uuid4

from ..ai.base import AIMessage, AIProvider, ProviderError
from ..schemas.agent import (
    AgentTeamEvent,
    AgentTeamSessionResponse,
    AgentTeamSessionStatus,
    AgentTeamWorker,
    AgentTeamWorkerStatus,
)

MAX_SESSIONS = 64
MAX_ACTIVE_SESSIONS_PER_OWNER = 3
MAX_ACTIVE_WORKERS_PER_OWNER = 24
SESSION_TTL = timedelta(hours=1)
MAX_EVENTS = 300
MAX_OUTPUT_CHARS = 6_000


@dataclass(frozen=True)
class TeamRole:
    name: str
    assignment: str


TEAM_ROLES = (
    TeamRole("Coordinator", "Break the goal into workstreams, dependencies, and review gates."),
    TeamRole("Metadata analyst", "Identify relevant EPM dimensions, members, cubes, and assumptions."),
    TeamRole("Rule designer", "Draft safe calculation logic and implementation considerations."),
    TeamRole("Validation lead", "Define concrete checks for totals, data quality, and regressions."),
    TeamRole("Safety reviewer", "Review risks, approvals, environment boundaries, and rollback needs."),
    TeamRole("Documentation lead", "Capture decisions, assumptions, open questions, and handoff notes."),
    TeamRole("Data analyst", "Assess source data, mappings, reconciliations, and edge cases."),
    TeamRole("Integration analyst", "Review interfaces, dependencies, schedules, and failure handling."),
    TeamRole("Performance analyst", "Look for scalability, calculation, and retrieval bottlenecks."),
    TeamRole("Test specialist", "Develop focused functional, negative, and acceptance test scenarios."),
    TeamRole("Change manager", "Outline stakeholder impact, communications, and adoption steps."),
    TeamRole("Final reviewer", "Challenge the proposed approach and summarize readiness gaps."),
)


class TeamSessionNotFound(LookupError):
    """The session is absent or is owned by a different caller."""


class TeamSessionConflict(RuntimeError):
    """The requested lifecycle action does not apply to the current state."""


class TeamSessionCapacityError(RuntimeError):
    """The bounded ephemeral registry has no safe slot to reclaim."""


class TeamSessionOwnerCapacityError(RuntimeError):
    """One owner has reached the active-session or provider-call budget."""


@dataclass
class _SessionRecord:
    owner: str
    provider: AIProvider
    snapshot: AgentTeamSessionResponse
    pause_gate: asyncio.Event
    workers: list[asyncio.Task[None]] = field(default_factory=list)
    supervisor: asyncio.Task[None] | None = None


def _now() -> datetime:
    return datetime.now(UTC)


class TeamSessionRegistry:
    """Owns ephemeral session state and the asyncio tasks that update it."""

    def __init__(
        self,
        *,
        max_sessions: int = MAX_SESSIONS,
        max_active_sessions_per_owner: int = MAX_ACTIVE_SESSIONS_PER_OWNER,
        max_active_workers_per_owner: int = MAX_ACTIVE_WORKERS_PER_OWNER,
        ttl: timedelta = SESSION_TTL,
    ) -> None:
        self._max_sessions = max_sessions
        self._max_active_sessions_per_owner = max_active_sessions_per_owner
        self._max_active_workers_per_owner = max_active_workers_per_owner
        self._ttl = ttl
        self._records: dict[str, _SessionRecord] = {}
        self._lock = RLock()

    def _cancel_task(self, task: asyncio.Task[None] | None) -> None:
        if task is None or task.done():
            return
        try:
            loop = task.get_loop()
            if loop.is_running():
                loop.call_soon_threadsafe(task.cancel)
        except RuntimeError:
            # A TestClient or application loop may already be closed.
            pass

    def _purge_locked(self) -> None:
        cutoff = _now() - self._ttl
        stale_ids = [
            session_id
            for session_id, record in self._records.items()
            if record.snapshot.updated_at < cutoff
        ]
        for session_id in stale_ids:
            record = self._records.pop(session_id)
            self._cancel_task(record.supervisor)
            for task in record.workers:
                self._cancel_task(task)

        if len(self._records) < self._max_sessions:
            return
        terminal = {
            AgentTeamSessionStatus.completed,
            AgentTeamSessionStatus.cancelled,
            AgentTeamSessionStatus.failed,
        }
        reclaimable = sorted(
            (
                record.snapshot.updated_at,
                session_id,
            )
            for session_id, record in self._records.items()
            if record.snapshot.status in terminal
        )
        while len(self._records) >= self._max_sessions and reclaimable:
            _updated_at, session_id = reclaimable.pop(0)
            self._records.pop(session_id, None)

    def _snapshot_locked(self, record: _SessionRecord) -> AgentTeamSessionResponse:
        # Never expose the mutable object that background tasks update.
        return deepcopy(record.snapshot)

    def _record_for_locked(self, session_id: str, owner: str) -> _SessionRecord:
        self._purge_locked()
        record = self._records.get(session_id)
        # Deliberately use the same exception for absent and cross-owner access.
        if record is None or record.owner != owner:
            raise TeamSessionNotFound("agent session not found")
        return record

    def _add_event_locked(
        self,
        record: _SessionRecord,
        event_type: str,
        message: str,
        *,
        agent_id: str | None = None,
    ) -> None:
        now = _now()
        record.snapshot.updated_at = now
        record.snapshot.events.append(
            AgentTeamEvent(
                id=str(uuid4()),
                type=event_type,
                message=message,
                agent_id=agent_id,
                created_at=now,
            )
        )
        if len(record.snapshot.events) > MAX_EVENTS:
            del record.snapshot.events[: len(record.snapshot.events) - MAX_EVENTS]

    def _recompute_progress_locked(self, record: _SessionRecord) -> None:
        record.snapshot.progress = round(
            sum(agent.progress for agent in record.snapshot.agents)
            / len(record.snapshot.agents)
        )
        record.snapshot.updated_at = _now()

    async def start(
        self,
        *,
        owner: str,
        goal: str,
        project_id: str | None,
        agent_count: int,
        provider: AIProvider,
    ) -> AgentTeamSessionResponse:
        now = _now()
        session_id = str(uuid4())
        agents = [
            AgentTeamWorker(
                id=str(uuid4()),
                role=role.name,
                assignment=role.assignment,
                status=AgentTeamWorkerStatus.queued,
                progress=0,
                activity="Waiting for the team to start.",
            )
            for role in TEAM_ROLES[:agent_count]
        ]
        snapshot = AgentTeamSessionResponse(
            id=session_id,
            goal=goal,
            project_id=project_id,
            status=AgentTeamSessionStatus.running,
            agent_count=agent_count,
            progress=0,
            created_at=now,
            updated_at=now,
            agents=agents,
            events=[],
        )
        pause_gate = asyncio.Event()
        pause_gate.set()
        record = _SessionRecord(
            owner=owner,
            provider=provider,
            snapshot=snapshot,
            pause_gate=pause_gate,
        )
        with self._lock:
            self._purge_locked()
            if len(self._records) >= self._max_sessions:
                raise TeamSessionCapacityError(
                    "agent session capacity reached; wait for a running session to finish"
                )
            terminal = {
                AgentTeamSessionStatus.completed,
                AgentTeamSessionStatus.cancelled,
                AgentTeamSessionStatus.failed,
            }
            active_for_owner = [
                existing
                for existing in self._records.values()
                if existing.owner == owner and existing.snapshot.status not in terminal
            ]
            if len(active_for_owner) >= self._max_active_sessions_per_owner:
                raise TeamSessionOwnerCapacityError(
                    "active agent-session limit reached for this user"
                )
            active_workers = sum(
                existing.snapshot.agent_count for existing in active_for_owner
            )
            if active_workers + agent_count > self._max_active_workers_per_owner:
                raise TeamSessionOwnerCapacityError(
                    "active agent-worker limit reached for this user"
                )
            self._records[session_id] = record
            self._add_event_locked(
                record,
                "sessionStarted",
                f"Started {agent_count} parallel role workers.",
            )
            for index in range(agent_count):
                record.workers.append(
                    asyncio.create_task(
                        self._run_worker(record, index),
                        name=f"epmw-team-{session_id}-{index}",
                    )
                )
            record.supervisor = asyncio.create_task(
                self._supervise(record),
                name=f"epmw-team-{session_id}-supervisor",
            )
            return self._snapshot_locked(record)

    async def _wait_until_runnable(self, record: _SessionRecord) -> bool:
        await record.pause_gate.wait()
        with self._lock:
            return record.snapshot.status not in {
                AgentTeamSessionStatus.cancelled,
                AgentTeamSessionStatus.failed,
            }

    def _system_prompt(self, worker: AgentTeamWorker) -> str:
        return (
            f"EPM_TEAM_ROLE: {worker.role}\n"
            f"Assignment: {worker.assignment}\n"
            "You are one role worker in an ephemeral EPM planning sandbox. "
            "Return concise, useful analysis with specific findings, assumptions, and next steps. "
            "You have no browser, screen-share, connector, deployment, or write access. "
            "Do not claim to have inspected a live tenant or changed EPM. "
            "Frame tenant-specific statements as checks or recommendations. "
            "Keep the answer under 700 words."
        )

    async def _run_worker(self, record: _SessionRecord, index: int) -> None:
        worker = record.snapshot.agents[index]
        try:
            if not await self._wait_until_runnable(record):
                return
            with self._lock:
                now = _now()
                worker.status = AgentTeamWorkerStatus.running
                worker.progress = 15
                worker.activity = f"Analyzing the goal as {worker.role.lower()}."
                worker.started_at = now
                self._add_event_locked(
                    record,
                    "agentStarted",
                    f"{worker.role} started its analysis.",
                    agent_id=worker.id,
                )
                self._recompute_progress_locked(record)

            output = await record.provider.complete(
                [AIMessage(role="user", content=record.snapshot.goal)],
                system=self._system_prompt(worker),
                temperature=0.2,
                max_tokens=900,
            )

            if not await self._wait_until_runnable(record):
                return
            with self._lock:
                if record.snapshot.status == AgentTeamSessionStatus.cancelled:
                    return
                worker.output = output.strip()[:MAX_OUTPUT_CHARS]
                worker.status = AgentTeamWorkerStatus.completed
                worker.progress = 100
                worker.activity = "Analysis complete and ready for review."
                worker.completed_at = _now()
                self._add_event_locked(
                    record,
                    "agentCompleted",
                    f"{worker.role} completed its analysis.",
                    agent_id=worker.id,
                )
                self._recompute_progress_locked(record)
        except asyncio.CancelledError:
            with self._lock:
                if worker.status not in {
                    AgentTeamWorkerStatus.completed,
                    AgentTeamWorkerStatus.failed,
                }:
                    worker.status = AgentTeamWorkerStatus.cancelled
                    worker.activity = "Cancelled."
                    worker.completed_at = _now()
                    self._recompute_progress_locked(record)
            raise
        except Exception as exc:
            message = exc.message if isinstance(exc, ProviderError) else str(exc)
            with self._lock:
                worker.status = AgentTeamWorkerStatus.failed
                worker.error = (message or "Provider request failed")[:500]
                worker.activity = "This worker failed; the remaining workers continued."
                worker.completed_at = _now()
                self._add_event_locked(
                    record,
                    "agentFailed",
                    f"{worker.role} failed: {worker.error}",
                    agent_id=worker.id,
                )
                self._recompute_progress_locked(record)

    async def _supervise(self, record: _SessionRecord) -> None:
        try:
            await asyncio.gather(*record.workers, return_exceptions=True)
        except asyncio.CancelledError:
            return
        with self._lock:
            if record.snapshot.status == AgentTeamSessionStatus.cancelled:
                return
            failed = sum(
                agent.status == AgentTeamWorkerStatus.failed
                for agent in record.snapshot.agents
            )
            record.snapshot.status = (
                AgentTeamSessionStatus.failed
                if failed
                else AgentTeamSessionStatus.completed
            )
            record.snapshot.progress = 100
            record.snapshot.completed_at = _now()
            if failed == len(record.snapshot.agents):
                summary = "All role workers failed."
            elif failed:
                summary = (
                    f"Team finished with {failed} failed worker(s); "
                    "review the successful outputs and errors."
                )
            else:
                summary = "All role workers completed."
            self._add_event_locked(
                record,
                "sessionFailed" if failed else "sessionCompleted",
                summary,
            )

    def get(self, session_id: str, owner: str) -> AgentTeamSessionResponse:
        with self._lock:
            record = self._record_for_locked(session_id, owner)
            return self._snapshot_locked(record)

    def pause(self, session_id: str, owner: str) -> AgentTeamSessionResponse:
        with self._lock:
            record = self._record_for_locked(session_id, owner)
            if record.snapshot.status != AgentTeamSessionStatus.running:
                raise TeamSessionConflict("only a running session can be paused")
            record.snapshot.status = AgentTeamSessionStatus.paused
            record.pause_gate.clear()
            for worker in record.snapshot.agents:
                if worker.status in {
                    AgentTeamWorkerStatus.queued,
                    AgentTeamWorkerStatus.running,
                }:
                    worker.status = AgentTeamWorkerStatus.paused
                    worker.activity = "Paused; provider output will not be published until resumed."
            self._add_event_locked(record, "sessionPaused", "Paused the team session.")
            return self._snapshot_locked(record)

    def resume(self, session_id: str, owner: str) -> AgentTeamSessionResponse:
        with self._lock:
            record = self._record_for_locked(session_id, owner)
            if record.snapshot.status != AgentTeamSessionStatus.paused:
                raise TeamSessionConflict("only a paused session can be resumed")
            record.snapshot.status = AgentTeamSessionStatus.running
            for worker in record.snapshot.agents:
                if worker.status == AgentTeamWorkerStatus.paused:
                    worker.status = AgentTeamWorkerStatus.running
                    worker.activity = "Resuming analysis."
            record.pause_gate.set()
            self._add_event_locked(record, "sessionResumed", "Resumed the team session.")
            return self._snapshot_locked(record)

    def cancel(self, session_id: str, owner: str) -> AgentTeamSessionResponse:
        with self._lock:
            record = self._record_for_locked(session_id, owner)
            if record.snapshot.status in {
                AgentTeamSessionStatus.completed,
                AgentTeamSessionStatus.cancelled,
                AgentTeamSessionStatus.failed,
            }:
                raise TeamSessionConflict("only a running or paused session can be cancelled")
            record.snapshot.status = AgentTeamSessionStatus.cancelled
            record.snapshot.completed_at = _now()
            record.pause_gate.set()
            for worker in record.snapshot.agents:
                if worker.status not in {
                    AgentTeamWorkerStatus.completed,
                    AgentTeamWorkerStatus.failed,
                }:
                    worker.status = AgentTeamWorkerStatus.cancelled
                    worker.activity = "Cancelled."
                    worker.completed_at = _now()
            self._add_event_locked(record, "sessionCancelled", "Cancelled the team session.")
            for task in record.workers:
                self._cancel_task(task)
            self._cancel_task(record.supervisor)
            return self._snapshot_locked(record)

    async def shutdown(self) -> None:
        """Cancel outstanding work (used by tests and graceful app shutdowns)."""
        with self._lock:
            records = list(self._records.values())
            self._records.clear()
        tasks: list[asyncio.Task[None]] = []
        for record in records:
            for task in [*record.workers, record.supervisor]:
                if task is not None and not task.done():
                    task.cancel()
                    tasks.append(task)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


team_sessions = TeamSessionRegistry()
