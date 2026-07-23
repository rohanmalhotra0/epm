"""Deterministic local provider (spec sections 11, 42).

Requires no API key and no network, so EPM Wizard is fully usable out of the box.
The heavy lifting (form/rule/context/deploy workflows) runs through the
deterministic skill engine; this provider produces the natural-language glue and
free-chat fallback. Given the same input it returns the same output.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import AsyncIterator

from .base import AIMessage, AIProvider, ProviderConfig, StreamChunk, StreamDone, TextDelta, Usage


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


EMBEDDING_DIM = 64


def _hash_embedding(text: str) -> list[float]:
    """Deterministic 64-dim unit vector from sha256 — a pure function of the
    text, so identical inputs always embed identically (no network, no model)."""
    raw: list[float] = []
    for block in range(EMBEDDING_DIM // 32):
        digest = hashlib.sha256(f"{block}:{text}".encode()).digest()  # 32 bytes
        raw.extend(b / 127.5 - 1.0 for b in digest)
    norm = math.sqrt(sum(v * v for v in raw)) or 1.0
    return [v / norm for v in raw]


class MockProvider(AIProvider):
    capabilities = {
        "streaming": True,
        "tools": True,  # handled deterministically by the orchestrator
        "structured": True,
        "attachments": False,
        "embeddings": True,  # deterministic local hash embeddings
        "contextWindow": 200_000,
    }

    def __init__(self, config: ProviderConfig | None = None) -> None:
        super().__init__(config or ProviderConfig(provider_type="mock", default_model="epmw-local-1"))

    async def list_models(self) -> list[str]:
        return ["epmw-local-1", "epmw-local-fast"]

    async def test_connection(self) -> dict:
        return {"ok": True, "provider": "mock", "models": await self.list_models(),
                "message": "Local deterministic provider — always available, no network."}

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        return [_hash_embedding(t) for t in texts]

    def _respond(self, messages: list[AIMessage], system: str | None) -> str:
        # A canned-but-contextual answer. If the orchestrator asked for a specific
        # composition via the system prompt, honour a few directives.
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        if system and system.startswith("COMPOSE:"):
            return system[len("COMPOSE:"):].strip()
        if system and system.startswith("EPM_TEAM_ROLE:"):
            role = system.splitlines()[0].partition(":")[2].strip() or "Specialist"
            assignment = next(
                (
                    line.partition(":")[2].strip()
                    for line in system.splitlines()
                    if line.startswith("Assignment:")
                ),
                "Analyze the task from this role's perspective.",
            )
            return (
                f"{role} analysis\n\n"
                f"Focus: {assignment}\n\n"
                f"For “{last_user.strip()[:240]}”, start by confirming the project scope, "
                "target application and cube, environment classification, relevant metadata, "
                "and the expected business outcome. Treat tenant-specific details as assumptions "
                "until they are verified against project context.\n\n"
                "Recommended next steps:\n"
                "1. Record the inputs, dependencies, and acceptance criteria for this workstream.\n"
                "2. Validate the proposal with read-only metadata and reconciliation checks.\n"
                "3. Document exceptions, required approvals, and a rollback or recovery path.\n\n"
                "No live tenant, browser, or screen was accessed, and no EPM changes were made."
            )
        text = last_user.strip()
        return (
            "I'm the EPM Wizard local assistant (deterministic demo provider). "
            "I can build and preview data forms, run business rules, inspect your EPM "
            "context, and prepare deployments — all locally.\n\n"
            f"You said: “{text[:200]}”.\n\n"
            "Try one of these: `/forms create an Actuals form`, `what cubes and dimensions exist?`, "
            "`/rules run the IR rule`, or `/context build`. To use an external model for open-ended "
            "answers, add a provider in Settings."
        )

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
        text = self._respond(messages, system)
        emitted = 0
        for token in _tokenize(text):
            if cancel is not None and cancel.is_set():
                yield StreamDone(reason="cancelled")
                return
            emitted += 1
            yield TextDelta(token)
        yield Usage(
            input_tokens=sum(_estimate_tokens(m.content) for m in messages),
            output_tokens=_estimate_tokens(text),
        )
        yield StreamDone(reason="stop")


def _tokenize(text: str) -> list[str]:
    # word-ish streaming so the UI shows incremental tokens
    out: list[str] = []
    word = ""
    for ch in text:
        word += ch
        if ch in " \n":
            out.append(word)
            word = ""
    if word:
        out.append(word)
    return out
