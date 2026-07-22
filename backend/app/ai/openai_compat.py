"""OpenAI-compatible provider — covers OpenAI, OpenRouter, Ollama and any generic
OpenAI-compatible endpoint (spec section 11)."""

from __future__ import annotations

import json
import os
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
    "together": "https://api.together.xyz/v1",
    "ollama": "http://localhost:11434/v1",
    "generic": "http://localhost:8080/v1",
}
# Finite streaming timeout so a stalled upstream errors instead of hanging forever.
_STREAM_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)


class OpenAICompatibleProvider(AIProvider):
    capabilities = {"streaming": True, "tools": True, "structured": True,
                    "attachments": False, "contextWindow": 128_000, "embeddings": True,
                    # The wire format (multi-part content with image_url parts) is
                    # generic to the OpenAI-compatible spec; whether a given model
                    # actually attends to the images is up to the deployment (e.g. a
                    # Qwen2.5-VL endpoint). A text-only model harmlessly ignores or
                    # errors on image parts — the caller picks a vision-capable
                    # model via the "vision" role before sending images.
                    "vision": True}

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
            payload = resp.json()
            # OpenAI-style APIs wrap the catalog in {"data": [...]}; Together
            # returns a bare top-level list.
            data = payload.get("data", []) if isinstance(payload, dict) else payload
            return [m.get("id") for m in data if isinstance(m, dict) and m.get("id")]
        except httpx.HTTPError as exc:
            raise ProviderError(f"Could not list models: {exc}") from exc

    async def test_connection(self) -> dict:
        models = await self.list_models()
        return {"ok": True, "provider": self.config.provider_type, "models": models[:20]}

    @property
    def embeddings_model(self) -> str:
        # profile role model -> env -> built-in. Precise RAG cache keying: vectors
        # are re-embedded when this changes.
        return (self.config.role_models.get("embedding")
                or os.environ.get("OPENAI_EMBEDDINGS_MODEL", "text-embedding-3-small"))

    @property
    def vision_model(self) -> str:
        # profile role model -> env -> the chat default. A separate role lets a
        # deployment pair a code model (chat/fast/structured/code) with a distinct
        # vision model (e.g. Qwen2.5-Coder-32B for text, Qwen2.5-VL-7B for
        # screenshots) on the same OpenAI-compatible endpoint.
        return (self.config.role_models.get("vision")
                or os.environ.get("OPENAI_VISION_MODEL")
                or self.config.default_model or "gpt-4o-mini")

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        """Embed texts via the OpenAI-compatible /embeddings endpoint (RAG grounding).

        Model resolution: explicit argument -> the provider's ``embeddings_model``
        (profile role model -> OPENAI_EMBEDDINGS_MODEL env -> text-embedding-3-small).
        Batched (<=100 inputs per request — large RAG corpora would otherwise
        exceed the API's per-request input limits); vectors are in input order.
        """
        model_id = model or self.embeddings_model
        vectors: list[list[float]] = []
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                for start in range(0, len(texts), 100):
                    body = {"model": model_id, "input": texts[start:start + 100]}
                    resp = await client.post(f"{self.base_url}/embeddings",
                                             headers=self._headers(), json=body)
                    if resp.status_code >= 400:
                        detail = resp.text[:300]
                        raise ProviderError(f"Provider embeddings error {resp.status_code}: {detail}",
                                            category="authentication" if resp.status_code == 401 else "aiProvider",
                                            retryable=resp.status_code == 429)
                    data = sorted(resp.json().get("data", []), key=lambda item: item.get("index", 0))
                    vectors.extend(item["embedding"] for item in data)
            return vectors
        except httpx.HTTPError as exc:
            raise ProviderError(f"Embeddings request failed: {exc}", retryable=True) from exc

    async def stream(
        self, messages: list[AIMessage], *, system: str | None = None, model: str | None = None,
        temperature: float = 0.2, max_tokens: int = 1024, cancel=None,
    ) -> AsyncIterator[StreamChunk]:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend({"role": m.role, "content": _content_parts(m)} for m in messages)
        # A message carrying screenshots routes to the vision role model unless
        # the caller already pinned an explicit model (e.g. the agent loop
        # picking Qwen2.5-VL for a screen-grounding step).
        has_images = any(m.images for m in messages)
        body = {
            "model": model or (self.vision_model if has_images else self.config.default_model) or "gpt-4o-mini",
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


def _content_parts(message: AIMessage) -> str | list[dict]:
    """Plain string for a text-only message (the unchanged, universally-
    supported wire shape); an OpenAI-style multi-part array (image_url parts
    + a trailing text part) once the message carries screenshots."""
    if not message.images:
        return message.content
    parts: list[dict] = [{"type": "image_url", "image_url": {"url": url}} for url in message.images]
    if message.content:
        parts.append({"type": "text", "text": message.content})
    return parts


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
