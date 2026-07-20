"""Embeddings adapters for RAG grounding: base default, Mock determinism,
watsonx.ai /ml/v1/text/embeddings and OpenAI-compatible /embeddings.

No network: httpx posts and the IAM token helper are monkeypatched.
"""

from __future__ import annotations

import json
import math

import httpx
import pytest

from app.ai.base import AIProvider, ProviderConfig, ProviderError, StreamDone
from app.ai.mock import MockProvider
from app.ai.openai_compat import OpenAICompatibleProvider
from app.ai.watsonx import API_VERSION, WatsonxProvider


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


# ---- watsonx.ai ---------------------------------------------------------------


def _watsonx(monkeypatch, **env) -> WatsonxProvider:
    monkeypatch.delenv("WATSONX_PROJECT_ID", raising=False)
    monkeypatch.delenv("WATSONX_SPACE_ID", raising=False)
    monkeypatch.delenv("WATSONX_EMBEDDINGS_MODEL_ID", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return WatsonxProvider(ProviderConfig(
        provider_type="watsonx",
        base_url="https://us-south.ml.cloud.ibm.com?project_id=proj-1",
        api_key="k",
    ))


def _patch_watsonx_network(monkeypatch, calls: list) -> None:
    async def fake_token(self, client):
        return "tok-123"

    async def fake_post(self, url, *, params=None, headers=None, json=None, data=None):
        calls.append({"url": url, "params": params, "headers": headers, "json": json})
        inputs = json["inputs"]
        return _FakeResponse({"results": [{"embedding": [float(len(t)), 1.0]} for t in inputs]})

    monkeypatch.setattr(WatsonxProvider, "_bearer_token", fake_token)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)


async def test_watsonx_embed_url_version_scope_and_default_model(monkeypatch):
    provider = _watsonx(monkeypatch)
    calls: list = []
    _patch_watsonx_network(monkeypatch, calls)

    vectors = await provider.embed(["alpha", "be"])

    assert vectors == [[5.0, 1.0], [2.0, 1.0]]
    assert len(calls) == 1
    call = calls[0]
    assert call["url"] == "https://us-south.ml.cloud.ibm.com/ml/v1/text/embeddings"
    assert call["params"] == {"version": API_VERSION}
    assert call["headers"]["Authorization"] == "Bearer tok-123"
    assert call["json"]["model_id"] == "ibm/slate-125m-english-rtrvr"
    assert call["json"]["project_id"] == "proj-1"  # scope injected
    assert call["json"]["inputs"] == ["alpha", "be"]


async def test_watsonx_embed_model_resolution(monkeypatch):
    provider = _watsonx(monkeypatch, WATSONX_EMBEDDINGS_MODEL_ID="ibm/slate-30m-english-rtrvr")
    calls: list = []
    _patch_watsonx_network(monkeypatch, calls)

    await provider.embed(["x"])
    assert calls[0]["json"]["model_id"] == "ibm/slate-30m-english-rtrvr"

    # explicit argument wins over the environment variable
    await provider.embed(["x"], model="ibm/custom-embedder")
    assert calls[1]["json"]["model_id"] == "ibm/custom-embedder"


async def test_watsonx_embed_batches_over_100_inputs_in_order(monkeypatch):
    provider = _watsonx(monkeypatch)
    calls: list = []
    _patch_watsonx_network(monkeypatch, calls)

    texts = [f"t{'x' * (i % 7)}{i}" for i in range(250)]
    vectors = await provider.embed(texts)

    assert [len(c["json"]["inputs"]) for c in calls] == [100, 100, 50]
    assert calls[0]["json"]["inputs"][0] == texts[0]
    assert calls[2]["json"]["inputs"][-1] == texts[-1]
    # concatenated in input order
    assert vectors == [[float(len(t)), 1.0] for t in texts]


async def test_watsonx_embed_http_error_becomes_provider_error(monkeypatch):
    provider = _watsonx(monkeypatch)

    async def fake_token(self, client):
        return "tok-123"

    async def fake_post(self, url, *, params=None, headers=None, json=None, data=None):
        return _FakeResponse({"errors": [{"message": "no such model"}]}, status_code=404)

    monkeypatch.setattr(WatsonxProvider, "_bearer_token", fake_token)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    with pytest.raises(ProviderError) as err:
        await provider.embed(["x"])
    assert "404" in err.value.message


def test_watsonx_chat_model_resolution(monkeypatch):
    provider = _watsonx(monkeypatch)
    monkeypatch.delenv("WATSONX_CHAT_MODEL_ID", raising=False)
    assert provider._chat_model(None) == "ibm/granite-3-8b-instruct"
    monkeypatch.setenv("WATSONX_CHAT_MODEL_ID", "meta-llama/llama-3-3-70b-instruct")
    assert provider._chat_model(None) == "meta-llama/llama-3-3-70b-instruct"
    provider.config.default_model = "ibm/granite-13b-chat-v2"
    assert provider._chat_model(None) == "ibm/granite-13b-chat-v2"  # profile beats env
    assert provider._chat_model("explicit/model") == "explicit/model"  # arg beats all


def test_watsonx_capabilities_declare_embeddings():
    assert WatsonxProvider.capabilities["embeddings"] is True


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
