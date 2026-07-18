"""OpenAI-compatible provider — covers OpenAI, OpenRouter, Ollama and any generic
OpenAI-compatible endpoint (spec section 11)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from .base import (
    AIMessage,
    AIProvider,
    ProviderConfig,
    ProviderError,
    StreamChunk,
    StreamDone,
    TextDelta,
    Usage,
)

_DEFAULT_BASE = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "ollama": "http://localhost:11434/v1",
    "generic": "http://localhost:8080/v1",
}
# Finite streaming timeout so a stalled upstream errors instead of hanging forever.
_STREAM_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)


class OpenAICompatibleProvider(AIProvider):
    capabilities = {"streaming": True, "tools": True, "structured": True,
                    "attachments": False, "contextWindow": 128_000}

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self.base_url = (config.base_url or _DEFAULT_BASE.get(config.provider_type, _DEFAULT_BASE["generic"])).rstrip("/")

    def _headers(self) -> dict:
        headers = {"content-type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    async def list_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(f"{self.base_url}/models", headers=self._headers())
            if resp.status_code == 401:
                raise ProviderError("The provider rejected the API key.", category="authentication")
            resp.raise_for_status()
            data = resp.json().get("data", [])
            return [m.get("id") for m in data if m.get("id")]
        except httpx.HTTPError as exc:
            raise ProviderError(f"Could not list models: {exc}") from exc

    async def test_connection(self) -> dict:
        models = await self.list_models()
        return {"ok": True, "provider": self.config.provider_type, "models": models[:20]}

    async def stream(
        self, messages: list[AIMessage], *, system: str | None = None, model: str | None = None,
        temperature: float = 0.2, max_tokens: int = 1024, cancel=None,
    ) -> AsyncIterator[StreamChunk]:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend({"role": m.role, "content": m.content} for m in messages)
        body = {
            "model": model or self.config.default_model or "gpt-4o-mini",
            "messages": msgs,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            # Without this, OpenAI-compatible backends emit no usage chunk while
            # streaming, so token accounting was always 0. Backends that don't
            # support it (some Ollama builds) ignore the field harmlessly.
            "stream_options": {"include_usage": True},
        }
        try:
            async with httpx.AsyncClient(timeout=_STREAM_TIMEOUT) as client:
                async with client.stream("POST", f"{self.base_url}/chat/completions",
                                         headers=self._headers(), json=body) as resp:
                    if resp.status_code >= 400:
                        detail = (await resp.aread()).decode("utf-8", "replace")[:300]
                        raise ProviderError(f"Provider error {resp.status_code}: {detail}",
                                            category="authentication" if resp.status_code == 401 else "aiProvider",
                                            retryable=resp.status_code == 429)
                    async for line in resp.aiter_lines():
                        if cancel is not None and cancel.is_set():
                            yield StreamDone(reason="cancelled")
                            return
                        for chunk in _parse_line(line):
                            yield chunk
        except httpx.HTTPError as exc:
            raise ProviderError(f"Streaming failed: {exc}", retryable=True) from exc
        yield StreamDone()


def _parse_line(line: str) -> list[StreamChunk]:
    if not line or not line.startswith("data:"):
        return []
    payload = line[len("data:"):].strip()
    if not payload or payload == "[DONE]":
        return []
    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        return []
    out: list[StreamChunk] = []
    for choice in event.get("choices", []):
        text = (choice.get("delta") or {}).get("content")
        if text:
            out.append(TextDelta(text))
    if event.get("usage"):
        u = event["usage"]
        out.append(Usage(input_tokens=u.get("prompt_tokens", 0), output_tokens=u.get("completion_tokens", 0)))
    return out
