"""Google Gemini provider (streaming via generateContent)."""

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

DEFAULT_BASE = "https://generativelanguage.googleapis.com"


class GeminiProvider(AIProvider):
    capabilities = {"streaming": True, "tools": True, "structured": True,
                    "attachments": True, "contextWindow": 1_000_000}

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self.base_url = (config.base_url or DEFAULT_BASE).rstrip("/")

    def _key(self) -> str:
        if not self.config.api_key:
            raise ProviderError("Gemini API key is not configured.", category="authentication")
        return self.config.api_key

    async def list_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(f"{self.base_url}/v1beta/models", params={"key": self._key()})
            resp.raise_for_status()
            return [m["name"].split("/")[-1] for m in resp.json().get("models", [])]
        except httpx.HTTPError as exc:
            raise ProviderError(f"Could not list Gemini models: {exc}") from exc

    async def test_connection(self) -> dict:
        return {"ok": True, "provider": "gemini", "models": (await self.list_models())[:20]}

    async def stream(
        self, messages: list[AIMessage], *, system: str | None = None, model: str | None = None,
        temperature: float = 0.2, max_tokens: int = 1024, cancel=None,
    ) -> AsyncIterator[StreamChunk]:
        model = model or self.config.default_model or "gemini-1.5-flash"
        contents = [
            {"role": "model" if m.role == "assistant" else "user", "parts": [{"text": m.content}]}
            for m in messages if m.role != "system"
        ]
        body = {"contents": contents, "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        url = f"{self.base_url}/v1beta/models/{model}:streamGenerateContent"
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("POST", url, params={"key": self._key(), "alt": "sse"}, json=body) as resp:
                    if resp.status_code >= 400:
                        detail = (await resp.aread()).decode("utf-8", "replace")[:300]
                        raise ProviderError(f"Gemini error {resp.status_code}: {detail}",
                                            retryable=resp.status_code == 429)
                    async for line in resp.aiter_lines():
                        if cancel is not None and cancel.is_set():
                            yield StreamDone(reason="cancelled")
                            return
                        for chunk in _parse_line(line):
                            yield chunk
        except httpx.HTTPError as exc:
            raise ProviderError(f"Gemini streaming failed: {exc}", retryable=True) from exc
        yield StreamDone()


def _parse_line(line: str) -> list[StreamChunk]:
    if not line or not line.startswith("data:"):
        return []
    payload = line[len("data:"):].strip()
    if not payload:
        return []
    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        return []
    out: list[StreamChunk] = []
    for cand in event.get("candidates", []):
        for part in (cand.get("content") or {}).get("parts", []):
            if part.get("text"):
                out.append(TextDelta(part["text"]))
    if event.get("usageMetadata"):
        u = event["usageMetadata"]
        out.append(Usage(input_tokens=u.get("promptTokenCount", 0), output_tokens=u.get("candidatesTokenCount", 0)))
    return out
