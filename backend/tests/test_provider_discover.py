"""Byte-level tests for POST /api/providers/models/discover.

The OpenAI-compatible probe is exercised end-to-end through the FastAPI app;
only the outbound HTTP transport is replaced (httpx.MockTransport), so header
construction, URL joining, JSON parsing and error mapping are all real.
"""

from __future__ import annotations

import httpx
import pytest

from app.ai import openai_compat

MODELS_JSON = {
    "object": "list",
    "data": [
        {"id": "llama3.2:3b", "object": "model"},
        {"id": "qwen2.5-coder:7b", "object": "model"},
        {"object": "model"},  # no id -> must be skipped
    ],
}


class _RecordingTransport(httpx.MockTransport):
    """MockTransport that keeps every request it served."""

    def __init__(self, handler):
        self.requests: list[httpx.Request] = []

        def _wrapped(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return handler(request)

        super().__init__(_wrapped)


def _patch_transport(monkeypatch: pytest.MonkeyPatch, handler) -> _RecordingTransport:
    """Route every AsyncClient created inside openai_compat through ``handler``."""
    transport = _RecordingTransport(handler)
    real_client = httpx.AsyncClient

    def _factory(**kwargs):
        kwargs["transport"] = transport
        return real_client(**kwargs)

    monkeypatch.setattr(openai_compat.httpx, "AsyncClient", _factory)
    return transport


def test_discover_returns_models_and_hits_models_path(client, monkeypatch):
    transport = _patch_transport(monkeypatch, lambda req: httpx.Response(200, json=MODELS_JSON))
    r = client.post("/api/providers/models/discover", json={"providerType": "ollama"})
    assert r.status_code == 200
    body = r.json()
    assert body["models"] == ["llama3.2:3b", "qwen2.5-coder:7b"]
    assert body["providerType"] == "ollama"
    # ollama default base URL is applied when none is given
    assert body["baseUrl"] == "http://localhost:11434/v1"
    (request,) = transport.requests
    assert str(request.url) == "http://localhost:11434/v1/models"
    # no key supplied -> no Authorization header leaves the app
    assert "authorization" not in request.headers


def test_discover_uses_custom_base_url_and_bearer_key(client, monkeypatch):
    transport = _patch_transport(monkeypatch, lambda req: httpx.Response(200, json={"data": []}))
    r = client.post(
        "/api/providers/models/discover",
        json={"providerType": "generic", "baseUrl": "http://box:9999/v1/", "apiKey": "sk-local-123"},
    )
    assert r.status_code == 200
    assert r.json() == {"providerType": "generic", "baseUrl": "http://box:9999/v1", "models": []}
    (request,) = transport.requests
    # trailing slash is normalised away before /models is appended
    assert str(request.url) == "http://box:9999/v1/models"
    assert request.headers["authorization"] == "Bearer sk-local-123"


def test_discover_unreachable_host_maps_to_502(client, monkeypatch):
    def _refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _patch_transport(monkeypatch, _refuse)
    r = client.post("/api/providers/models/discover", json={"providerType": "ollama"})
    assert r.status_code == 502
    assert "Could not list models" in r.json()["detail"]


def test_discover_rejected_key_maps_to_400(client, monkeypatch):
    _patch_transport(monkeypatch, lambda req: httpx.Response(401, json={"error": "bad key"}))
    r = client.post(
        "/api/providers/models/discover",
        json={"providerType": "openai", "apiKey": "sk-wrong"},
    )
    assert r.status_code == 400
    assert "rejected the API key" in r.json()["detail"]


def test_discover_mock_provider_needs_no_network(client):
    # the mock provider's list_models is pure Python; no transport patching
    r = client.post("/api/providers/models/discover", json={"providerType": "mock"})
    assert r.status_code == 200
    assert r.json()["models"], "mock provider should report at least one model"
