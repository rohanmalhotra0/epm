"""Deterministic local provider (spec sections 11, 42).

Requires no API key and no network, so EPM Wizard is fully usable out of the box.
The heavy lifting (form/rule/context/deploy workflows) runs through the
deterministic skill engine; this provider produces the natural-language glue and
free-chat fallback. Given the same input it returns the same output.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from .base import AIMessage, AIProvider, ProviderConfig, StreamChunk, StreamDone, TextDelta, Usage


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class MockProvider(AIProvider):
    capabilities = {
        "streaming": True,
        "tools": True,  # handled deterministically by the orchestrator
        "structured": True,
        "attachments": False,
        "contextWindow": 200_000,
    }

    def __init__(self, config: ProviderConfig | None = None) -> None:
        super().__init__(config or ProviderConfig(provider_type="mock", default_model="epmw-local-1"))

    async def list_models(self) -> list[str]:
        return ["epmw-local-1", "epmw-local-fast"]

    async def test_connection(self) -> dict:
        return {"ok": True, "provider": "mock", "models": await self.list_models(),
                "message": "Local deterministic provider — always available, no network."}

    def _respond(self, messages: list[AIMessage], system: str | None) -> str:
        # A canned-but-contextual answer. If the orchestrator asked for a specific
        # composition via the system prompt, honour a few directives.
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        if system and system.startswith("COMPOSE:"):
            return system[len("COMPOSE:"):].strip()
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
