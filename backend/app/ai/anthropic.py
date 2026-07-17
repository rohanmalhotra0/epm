"""Anthropic Messages API provider (streaming)."""

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

DEFAULT_BASE = "https://api.anthropic.com"
API_VERSION = "2023-06-01"


class AnthropicProvider(AIProvider):
    capabilities = {"streaming": True, "tools": True, "structured": True,
                    "attachments": True, "contextWindow": 200_000}

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self.base_url = (config.base_url or DEFAULT_BASE).rstrip("/")

    def _headers(self) -> dict:
        if not self.config.api_key:
            raise ProviderError("Anthropic API key is not configured.", category="authentication")
        return {
            "x-api-key": self.config.api_key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }

    async def list_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(f"{self.base_url}/v1/models", headers=self._headers())
            if resp.status_code == 401:
                raise ProviderError("Anthropic rejected the API key.", category="authentication")
            resp.raise_for_status()
            return [m["id"] for m in resp.json().get("data", [])]
        except httpx.HTTPError as exc:
            raise ProviderError(f"Could not list Anthropic models: {exc}") from exc

    async def test_connection(self) -> dict:
        models = await self.list_models()
        return {"ok": True, "provider": "anthropic", "models": models[:20]}

    async def stream(
        self, messages: list[AIMessage], *, system: str | None = None, model: str | None = None,
        temperature: float = 0.2, max_tokens: int = 1024, cancel=None,
    ) -> AsyncIterator[StreamChunk]:
        # NOTE: `temperature` (and top_p/top_k) are intentionally NOT sent.
        # Claude Opus 4.7+ reject any explicit sampling value with a 400
        # ("temperature is deprecated for this model"); omitting the field uses
        # the model default. `temperature` stays in the signature for interface
        # compatibility with the other providers. Steer determinism via the
        # prompt (e.g. "respond with strict JSON") instead.
        body = {
            "model": model or self.config.default_model or "claude-sonnet-5",
            "max_tokens": max_tokens,
            "stream": True,
            "messages": [{"role": m.role, "content": m.content} for m in messages if m.role != "system"],
        }
        if system:
            body["system"] = system
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("POST", f"{self.base_url}/v1/messages",
                                         headers=self._headers(), json=body) as resp:
                    if resp.status_code >= 400:
                        detail = (await resp.aread()).decode("utf-8", "replace")[:300]
                        raise ProviderError(f"Anthropic error {resp.status_code}: {detail}",
                                            category="authentication" if resp.status_code == 401 else "aiProvider",
                                            retryable=resp.status_code == 429)
                    async for line in resp.aiter_lines():
                        if cancel is not None and cancel.is_set():
                            yield StreamDone(reason="cancelled")
                            return
                        for chunk in _parse_event(line):
                            yield chunk
        except httpx.HTTPError as exc:
            raise ProviderError(f"Anthropic streaming failed: {exc}", retryable=True) from exc
        yield StreamDone()


def _parse_event(line: str) -> list[StreamChunk]:
    if not line or not line.startswith("data:"):
        return []
    payload = line[len("data:"):].strip()
    if not payload or payload == "[DONE]":
        return []
    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        return []
    etype = event.get("type")
    if etype == "content_block_delta":
        delta = event.get("delta", {})
        if delta.get("type") == "text_delta":
            return [TextDelta(delta.get("text", ""))]
    if etype == "message_delta":
        usage = event.get("usage", {})
        if usage:
            return [Usage(output_tokens=usage.get("output_tokens", 0))]
    return []
