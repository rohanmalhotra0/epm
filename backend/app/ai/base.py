"""Provider-independent AI layer (spec section 11).

A narrow interface every provider implements: model listing, connection test,
streaming, tool calling, structured output, cancellation, token usage and
normalised errors. Secrets are resolved by the registry and never logged.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field


@dataclass
class AIMessage:
    role: str  # user | assistant | system
    content: str


@dataclass
class ProviderConfig:
    provider_type: str
    base_url: str | None = None
    api_key: str | None = None
    default_model: str | None = None
    models: list[str] = field(default_factory=list)


@dataclass
class TextDelta:
    text: str


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class StreamDone:
    reason: str = "stop"


StreamChunk = TextDelta | ToolCall | Usage | StreamDone


class ProviderError(Exception):
    def __init__(self, message: str, *, category: str = "aiProvider", retryable: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.category = category
        self.retryable = retryable


class AIProvider(ABC):
    capabilities: dict = {
        "streaming": True,
        "tools": False,
        "structured": False,
        "attachments": False,
        "embeddings": False,
        "contextWindow": None,
    }

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    @property
    def name(self) -> str:
        return self.config.provider_type

    @abstractmethod
    async def list_models(self) -> list[str]: ...

    @abstractmethod
    async def test_connection(self) -> dict: ...

    @abstractmethod
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
        raise NotImplementedError
        yield  # pragma: no cover

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        """Return one embedding vector per input text (used by the RAG core for
        hybrid retrieval). Providers that support embeddings override this and
        set ``capabilities["embeddings"] = True``; the default reports the gap."""
        raise ProviderError("this provider does not support embeddings")

    async def complete(
        self, messages: list[AIMessage], *, system: str | None = None, model: str | None = None,
        temperature: float = 0.2, max_tokens: int = 1024,
    ) -> str:
        parts: list[str] = []
        async for chunk in self.stream(messages, system=system, model=model,
                                       temperature=temperature, max_tokens=max_tokens):
            if isinstance(chunk, TextDelta):
                parts.append(chunk.text)
        return "".join(parts)
