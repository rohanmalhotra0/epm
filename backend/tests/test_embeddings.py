"""Embeddings adapters for RAG grounding: base default, Mock determinism,
and OpenAI-compatible /embeddings.

No network: httpx posts are monkeypatched.
"""

from __future__ import annotations

import json
import math

import httpx
import pytest

from app.ai.base import AIProvider, ProviderConfig, ProviderError, StreamDone
from app.ai.mock import MockProvider
from app.ai.openai_compat import OpenAICompatibleProvider


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self) -> dict:
        return self._payload


# ---- AIProvider default -----------------------------------------------------


class _MinimalProvider(AIProvider):
    async def list_models(self):  # pragma: no cover - not exercised
        return []

    async def test_connection(self):  # pragma: no cover - not exercised
        return {"ok": True}

    async def stream(self, messages, *, system=None, model=None,
                     temperature=0.2, max_tokens=1024, cancel=None):
        yield StreamDone()  # pragma: no cover - not exercised


async def test_base_embed_default_raises_provider_error():
    provider = _MinimalProvider(ProviderConfig(provider_type="generic"))
    with pytest.raises(ProviderError):
        await provider.embed(["hello"])


def test_base_capabilities_declare_no_embeddings():
    assert AIProvider.capabilities.get("embeddings") is False


# ---- Mock provider (deterministic, offline) ----------------------------------


async def test_mock_embed_is_deterministic_normalized_64d():
    provider = MockProvider(ProviderConfig(provider_type="mock"))
    assert provider.capabilities.get("embeddings") is True

    first = await provider.embed(["Copy Working to Final", "OFS_Revenue"])
    second = await provider.embed(["Copy Working to Final", "OFS_Revenue"])
    assert first == second  # deterministic
    assert len(first) == 2
    for vector in first:
        assert len(vector) == 64
        assert math.isclose(math.sqrt(sum(v * v for v in vector)), 1.0, rel_tol=1e-6)
    # different texts embed differently
    assert first[0] != first[1]


# ---- OpenAI-compatible --------------------------------------------------------


def _patch_openai_network(monkeypatch, calls: list, *, shuffle_indices: bool = False) -> None:
    async def fake_post(self, url, *, params=None, headers=None, json=None, data=None):
        calls.append({"url": url, "headers": headers, "json": json})
        data_items = [{"index": i, "embedding": [float(i), 0.5]}
                      for i in range(len(json["input"]))]
        if shuffle_indices:
            data_items = list(reversed(data_items))
        return _FakeResponse({"data": data_items})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)


async def test_openai_compat_embed_body_and_default_model(monkeypatch):
    monkeypatch.delenv("OPENAI_EMBEDDINGS_MODEL", raising=False)
    provider = OpenAICompatibleProvider(ProviderConfig(provider_type="openai", api_key="sk-1"))
    calls: list = []
    _patch_openai_network(monkeypatch, calls)

    vectors = await provider.embed(["a", "b", "c"])

    assert calls[0]["url"] == "https://api.openai.com/v1/embeddings"
    assert calls[0]["json"] == {"model": "text-embedding-3-small", "input": ["a", "b", "c"]}
    assert calls[0]["headers"]["Authorization"] == "Bearer sk-1"
    assert vectors == [[0.0, 0.5], [1.0, 0.5], [2.0, 0.5]]


async def test_openai_compat_embed_model_env_and_index_sorting(monkeypatch):
    monkeypatch.setenv("OPENAI_EMBEDDINGS_MODEL", "custom-embed")
    provider = OpenAICompatibleProvider(ProviderConfig(provider_type="openai", api_key="sk-1"))
    calls: list = []
    _patch_openai_network(monkeypatch, calls, shuffle_indices=True)

    vectors = await provider.embed(["a", "b"])

    assert calls[0]["json"]["model"] == "custom-embed"
    # out-of-order data[] entries are re-sorted by index
    assert vectors == [[0.0, 0.5], [1.0, 0.5]]

    await provider.embed(["a"], model="arg-wins")
    assert calls[1]["json"]["model"] == "arg-wins"


async def test_openai_compat_embed_http_error_becomes_provider_error(monkeypatch):
    provider = OpenAICompatibleProvider(ProviderConfig(provider_type="openai", api_key="sk-1"))

    async def fake_post(self, url, *, params=None, headers=None, json=None, data=None):
        return _FakeResponse({"error": {"message": "bad key"}}, status_code=401)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    with pytest.raises(ProviderError) as err:
        await provider.embed(["x"])
    assert err.value.category == "authentication"


def test_openai_capabilities_declare_embeddings():
    assert OpenAICompatibleProvider.capabilities["embeddings"] is True


def test_openai_embeddings_model_prefers_profile_role_model(monkeypatch):
    monkeypatch.delenv("OPENAI_EMBEDDINGS_MODEL", raising=False)
    base = OpenAICompatibleProvider(ProviderConfig(provider_type="openai", api_key="k"))
    assert base.embeddings_model == "text-embedding-3-small"  # default
    monkeypatch.setenv("OPENAI_EMBEDDINGS_MODEL", "env/model")
    assert base.embeddings_model == "env/model"  # env beats default
    with_role = OpenAICompatibleProvider(ProviderConfig(
        provider_type="openai", api_key="k",
        role_models={"embedding": "text-embedding-3-large"}))
    assert with_role.embeddings_model == "text-embedding-3-large"  # profile beats env


def test_provider_from_profile_threads_role_models(monkeypatch):
    monkeypatch.delenv("OPENAI_EMBEDDINGS_MODEL", raising=False)
    from app.ai.registry import provider_from_profile
    from app.db.models import ProviderProfile

    profile = ProviderProfile(id="p1", name="oai", provider_type="openai",
                              base_url="https://api.openai.com/v1",
                              default_model="gpt-4o-mini",
                              role_models={"embedding": "text-embedding-3-large"})
    provider = provider_from_profile(profile)  # no DB write needed
    assert provider.config.role_models == {"embedding": "text-embedding-3-large"}
    assert provider.embeddings_model == "text-embedding-3-large"
