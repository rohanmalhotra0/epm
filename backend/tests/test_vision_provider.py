"""Vision plumbing for the OpenAI-compatible provider (computer-use agent groundwork).

A message can now carry screenshots (``AIMessage.images``, data URLs). The
OpenAI-compatible provider turns those into the standard multi-part
``image_url`` content shape and routes to a distinct "vision" role model
(e.g. pairing a Qwen2.5-Coder text model with a Qwen2.5-VL vision model on
the same endpoint) — a text-only message's wire shape is unchanged.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.ai.base import AIMessage, AIProvider, ProviderConfig, TextDelta
from app.ai.openai_compat import OpenAICompatibleProvider, _content_parts


class _RecordingTransport(httpx.MockTransport):
    def __init__(self, handler):
        self.requests: list[httpx.Request] = []

        def _wrapped(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return handler(request)

        super().__init__(_wrapped)


def _patch_transport(monkeypatch: pytest.MonkeyPatch, handler) -> _RecordingTransport:
    import app.ai.openai_compat as openai_compat

    transport = _RecordingTransport(handler)
    real_client = httpx.AsyncClient

    def _factory(**kwargs):
        kwargs["transport"] = transport
        return real_client(**kwargs)

    monkeypatch.setattr(openai_compat.httpx, "AsyncClient", _factory)
    return transport


def _sse_response(text: str = "ok") -> httpx.Response:
    body = f'data: {json.dumps({"choices": [{"delta": {"content": text}}]})}\n\ndata: [DONE]\n\n'
    return httpx.Response(200, content=body.encode())


# --- content-part shaping -----------------------------------------------------


def test_content_parts_text_only_stays_a_plain_string():
    msg = AIMessage(role="user", content="hello")
    assert _content_parts(msg) == "hello"


def test_content_parts_with_images_becomes_multipart():
    msg = AIMessage(role="user", content="what is this?",
                    images=["data:image/png;base64,AAAA", "data:image/png;base64,BBBB"])
    parts = _content_parts(msg)
    assert parts == [
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,BBBB"}},
        {"type": "text", "text": "what is this?"},
    ]


def test_content_parts_images_with_no_text_omits_text_part():
    msg = AIMessage(role="user", content="", images=["data:image/png;base64,AAAA"])
    parts = _content_parts(msg)
    assert parts == [{"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]


def test_aimessage_images_default_empty_and_backward_compatible():
    msg = AIMessage(role="user", content="hi")
    assert msg.images == []


# --- capability declarations ---------------------------------------------------


def test_base_provider_declares_no_vision_by_default():
    assert AIProvider.capabilities["vision"] is False


def test_openai_compat_declares_vision():
    assert OpenAICompatibleProvider.capabilities["vision"] is True


# --- wire behavior via stream() -------------------------------------------------


@pytest.mark.asyncio
async def test_stream_text_only_sends_plain_string_content(monkeypatch):
    transport = _patch_transport(monkeypatch, lambda req: _sse_response())
    provider = OpenAICompatibleProvider(ProviderConfig(provider_type="generic", default_model="qwen2.5-coder:32b"))
    chunks = [c async for c in provider.stream([AIMessage(role="user", content="hi")])]
    assert any(isinstance(c, TextDelta) for c in chunks)
    (request,) = transport.requests
    body = json.loads(request.content)
    assert body["messages"][0] == {"role": "user", "content": "hi"}
    assert body["model"] == "qwen2.5-coder:32b"  # no images -> the default/chat model, not vision


@pytest.mark.asyncio
async def test_stream_with_images_sends_multipart_and_routes_to_vision_model(monkeypatch):
    transport = _patch_transport(monkeypatch, lambda req: _sse_response())
    provider = OpenAICompatibleProvider(ProviderConfig(
        provider_type="generic", default_model="qwen2.5-coder:32b",
        role_models={"vision": "qwen2.5-vl:7b"},
    ))
    msg = AIMessage(role="user", content="what's on screen?", images=["data:image/png;base64,AAAA"])
    chunks = [c async for c in provider.stream([msg])]
    assert any(isinstance(c, TextDelta) for c in chunks)
    (request,) = transport.requests
    body = json.loads(request.content)
    assert body["model"] == "qwen2.5-vl:7b"  # routed to the vision role model
    assert body["messages"][0]["content"] == [
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
        {"type": "text", "text": "what's on screen?"},
    ]


@pytest.mark.asyncio
async def test_stream_explicit_model_overrides_vision_routing(monkeypatch):
    transport = _patch_transport(monkeypatch, lambda req: _sse_response())
    provider = OpenAICompatibleProvider(ProviderConfig(
        provider_type="generic", default_model="qwen2.5-coder:32b",
        role_models={"vision": "qwen2.5-vl:7b"},
    ))
    msg = AIMessage(role="user", content="look", images=["data:image/png;base64,AAAA"])
    _ = [c async for c in provider.stream([msg], model="pinned-model")]
    (request,) = transport.requests
    assert json.loads(request.content)["model"] == "pinned-model"


def test_vision_model_resolution_role_then_env_then_default(monkeypatch):
    # profile role model wins
    provider = OpenAICompatibleProvider(ProviderConfig(
        provider_type="generic", default_model="qwen2.5-coder:32b", role_models={"vision": "role-vl"}))
    assert provider.vision_model == "role-vl"

    # no role model -> env fallback
    provider = OpenAICompatibleProvider(ProviderConfig(provider_type="generic", default_model="qwen2.5-coder:32b"))
    monkeypatch.setenv("OPENAI_VISION_MODEL", "env-vl")
    assert provider.vision_model == "env-vl"
    monkeypatch.delenv("OPENAI_VISION_MODEL", raising=False)

    # neither -> the provider's chat default
    assert provider.vision_model == "qwen2.5-coder:32b"

    # nothing configured at all -> the hardcoded fallback
    bare = OpenAICompatibleProvider(ProviderConfig(provider_type="generic"))
    assert bare.vision_model == "gpt-4o-mini"
