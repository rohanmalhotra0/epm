"""IBM watsonx.ai provider (streaming via /ml/v1/text/chat_stream).

Auth is two-step, unlike the other providers: the stored key is an IBM Cloud
API key that is exchanged for a short-lived IAM bearer token at
iam.cloud.ibm.com, cached until shortly before expiry.

watsonx inference is scoped to a *project* (or deployment space). The project
id is resolved from, in order:
  1. a `project_id` query parameter on the profile's base URL
     (e.g. `https://us-south.ml.cloud.ibm.com?project_id=abc-123`),
  2. the WATSONX_PROJECT_ID environment variable
     (WATSONX_SPACE_ID selects a deployment space instead).
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import AsyncIterator
from urllib.parse import parse_qs, urlsplit, urlunsplit

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

DEFAULT_BASE = "https://us-south.ml.cloud.ibm.com"
DEFAULT_IAM_URL = "https://iam.cloud.ibm.com/identity/token"
DEFAULT_MODEL = "ibm/granite-3-8b-instruct"
DEFAULT_EMBEDDINGS_MODEL = "ibm/slate-125m-english-rtrvr"
API_VERSION = "2024-05-31"  # watsonx.ai REST `version` date parameter
_EMBED_BATCH = 100  # watsonx.ai caps embedding inputs per request
# Finite streaming timeout so a stalled upstream errors instead of hanging forever.
_STREAM_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)
_TOKEN_SAFETY_WINDOW = 60.0  # refresh the IAM token this many seconds early


class WatsonxProvider(AIProvider):
    capabilities = {"streaming": True, "tools": True, "structured": True,
                    "attachments": False, "contextWindow": 128_000, "embeddings": True}

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        base, project_from_url = _split_base_url(config.base_url or os.environ.get("WATSONX_URL") or DEFAULT_BASE)
        self.base_url = base
        self.project_id = project_from_url or os.environ.get("WATSONX_PROJECT_ID")
        self.space_id = None if self.project_id else os.environ.get("WATSONX_SPACE_ID")
        self.iam_url = os.environ.get("WATSONX_IAM_URL", DEFAULT_IAM_URL)
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    def _key(self) -> str:
        if not self.config.api_key:
            raise ProviderError("IBM Cloud API key is not configured.", category="authentication")
        return self.config.api_key

    async def _bearer_token(self, client: httpx.AsyncClient) -> str:
        if self._token and time.monotonic() < self._token_expires_at - _TOKEN_SAFETY_WINDOW:
            return self._token
        try:
            resp = await client.post(
                self.iam_url,
                data={"grant_type": "urn:ibm:params:oauth:grant-type:apikey", "apikey": self._key()},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"IBM IAM token exchange failed: {exc}", retryable=True) from exc
        if resp.status_code == 400 or resp.status_code == 401:
            raise ProviderError("IBM Cloud rejected the API key.", category="authentication")
        if resp.status_code >= 400:
            raise ProviderError(f"IBM IAM error {resp.status_code}: {resp.text[:300]}",
                                retryable=resp.status_code >= 500)
        payload = resp.json()
        self._token = payload.get("access_token")
        if not self._token:
            raise ProviderError("IBM IAM returned no access token.", category="authentication")
        self._token_expires_at = time.monotonic() + float(payload.get("expires_in", 3600))
        return self._token

    @property
    def embeddings_model(self) -> str:
        # Precise RAG cache keying: vectors are re-embedded when this changes.
        return os.environ.get("WATSONX_EMBEDDINGS_MODEL_ID") or DEFAULT_EMBEDDINGS_MODEL

    def _chat_model(self, model: str | None) -> str:
        """explicit arg -> provider profile -> WATSONX_CHAT_MODEL_ID env -> built-in."""
        return (model or self.config.default_model
                or os.environ.get("WATSONX_CHAT_MODEL_ID") or DEFAULT_MODEL)

    def _scope(self) -> dict:
        if self.project_id:
            return {"project_id": self.project_id}
        if self.space_id:
            return {"space_id": self.space_id}
        raise ProviderError(
            "watsonx.ai needs a project: set WATSONX_PROJECT_ID (or add ?project_id=... "
            "to the provider base URL, or WATSONX_SPACE_ID for a deployment space).",
            category="configuration",
        )

    async def list_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                token = await self._bearer_token(client)
                resp = await client.get(
                    f"{self.base_url}/ml/v1/foundation_model_specs",
                    params={"version": API_VERSION, "limit": 200},
                    headers={"Authorization": f"Bearer {token}"},
                )
            resp.raise_for_status()
            return [m["model_id"] for m in resp.json().get("resources", []) if m.get("model_id")]
        except httpx.HTTPError as exc:
            raise ProviderError(f"Could not list watsonx.ai models: {exc}") from exc

    async def test_connection(self) -> dict:
        models = await self.list_models()
        self._scope()  # fail fast in the connection test if no project is configured
        return {"ok": True, "provider": "watsonx", "models": models[:20]}

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        """Embed texts via /ml/v1/text/embeddings (used for RAG grounding).

        Model resolution: explicit argument -> WATSONX_EMBEDDINGS_MODEL_ID env
        var -> the slate retriever default. Inputs are batched (the API caps
        inputs per request); result vectors are concatenated in input order.
        """
        model_id = model or os.environ.get("WATSONX_EMBEDDINGS_MODEL_ID") or DEFAULT_EMBEDDINGS_MODEL
        url = f"{self.base_url}/ml/v1/text/embeddings"
        vectors: list[list[float]] = []
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                token = await self._bearer_token(client)
                for start in range(0, len(texts), _EMBED_BATCH):
                    batch = texts[start:start + _EMBED_BATCH]
                    resp = await client.post(
                        url,
                        params={"version": API_VERSION},
                        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                        json={"model_id": model_id, "inputs": batch, **self._scope()},
                    )
                    if resp.status_code >= 400:
                        detail = resp.text[:300]
                        raise ProviderError(
                            f"watsonx.ai embeddings error {resp.status_code}: {detail}",
                            category="authentication" if resp.status_code in (401, 403) else "aiProvider",
                            retryable=resp.status_code == 429,
                        )
                    vectors.extend(r["embedding"] for r in resp.json().get("results", []))
        except httpx.HTTPError as exc:
            raise ProviderError(f"watsonx.ai embeddings failed: {exc}", retryable=True) from exc
        return vectors

    async def stream(
        self, messages: list[AIMessage], *, system: str | None = None, model: str | None = None,
        temperature: float = 0.2, max_tokens: int = 1024, cancel=None,
    ) -> AsyncIterator[StreamChunk]:
        body = {
            "model_id": self._chat_model(model),
            **self._scope(),
            "messages": _to_chat_messages(messages, system),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        url = f"{self.base_url}/ml/v1/text/chat_stream"
        try:
            async with httpx.AsyncClient(timeout=_STREAM_TIMEOUT) as client:
                token = await self._bearer_token(client)
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                           "Accept": "text/event-stream"}
                async with client.stream("POST", url, params={"version": API_VERSION},
                                         headers=headers, json=body) as resp:
                    if resp.status_code >= 400:
                        detail = (await resp.aread()).decode("utf-8", "replace")[:300]
                        raise ProviderError(f"watsonx.ai error {resp.status_code}: {detail}",
                                            category="authentication" if resp.status_code in (401, 403) else "aiProvider",
                                            retryable=resp.status_code == 429)
                    async for line in resp.aiter_lines():
                        if cancel is not None and cancel.is_set():
                            yield StreamDone(reason="cancelled")
                            return
                        for chunk in _parse_line(line):
                            yield chunk
        except httpx.HTTPError as exc:
            raise ProviderError(f"watsonx.ai streaming failed: {exc}", retryable=True) from exc
        yield StreamDone()


def _split_base_url(raw: str) -> tuple[str, str | None]:
    """Return (base URL without query, project_id query param if present)."""
    parts = urlsplit(raw)
    project_id = (parse_qs(parts.query).get("project_id") or [None])[0]
    base = urlunsplit((parts.scheme, parts.netloc, parts.path, "", "")).rstrip("/")
    return base, project_id


def _to_chat_messages(messages: list[AIMessage], system: str | None) -> list[dict]:
    out: list[dict] = []
    if system:
        out.append({"role": "system", "content": system})
    for m in messages:
        if m.role == "system":
            out.append({"role": "system", "content": m.content})
        elif m.role == "assistant":
            out.append({"role": "assistant", "content": m.content})
        else:
            # watsonx chat requires user content as typed parts
            out.append({"role": "user", "content": [{"type": "text", "text": m.content}]})
    return out


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
