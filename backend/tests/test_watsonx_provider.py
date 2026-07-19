"""IBM watsonx.ai provider: URL/scope resolution, message mapping, SSE parsing."""

from __future__ import annotations

import pytest

from app.ai.base import AIMessage, ProviderConfig, ProviderError, TextDelta, Usage
from app.ai.registry import _class_for
from app.ai.watsonx import (
    WatsonxProvider,
    _parse_line,
    _split_base_url,
    _to_chat_messages,
)


def _provider(base_url: str | None = None, **env) -> WatsonxProvider:
    return WatsonxProvider(ProviderConfig(provider_type="watsonx", base_url=base_url, api_key="k"))


def test_registry_maps_watsonx_types():
    assert _class_for("watsonx") is WatsonxProvider
    assert _class_for("ibm") is WatsonxProvider


def test_split_base_url_extracts_project_id():
    base, project = _split_base_url("https://eu-de.ml.cloud.ibm.com?project_id=abc-123")
    assert base == "https://eu-de.ml.cloud.ibm.com"
    assert project == "abc-123"
    base, project = _split_base_url("https://us-south.ml.cloud.ibm.com/")
    assert base == "https://us-south.ml.cloud.ibm.com"
    assert project is None


def test_project_id_from_base_url_and_env(monkeypatch):
    monkeypatch.delenv("WATSONX_PROJECT_ID", raising=False)
    monkeypatch.delenv("WATSONX_SPACE_ID", raising=False)
    p = _provider("https://us-south.ml.cloud.ibm.com?project_id=from-url")
    assert p.project_id == "from-url"
    assert p._scope() == {"project_id": "from-url"}

    monkeypatch.setenv("WATSONX_PROJECT_ID", "from-env")
    assert _provider()._scope() == {"project_id": "from-env"}

    monkeypatch.delenv("WATSONX_PROJECT_ID", raising=False)
    monkeypatch.setenv("WATSONX_SPACE_ID", "space-1")
    assert _provider()._scope() == {"space_id": "space-1"}


def test_missing_project_is_a_clear_configuration_error(monkeypatch):
    monkeypatch.delenv("WATSONX_PROJECT_ID", raising=False)
    monkeypatch.delenv("WATSONX_SPACE_ID", raising=False)
    with pytest.raises(ProviderError) as err:
        _provider()._scope()
    assert err.value.category == "configuration"
    assert "WATSONX_PROJECT_ID" in err.value.message


def test_chat_message_mapping_wraps_user_content():
    msgs = _to_chat_messages(
        [AIMessage(role="user", content="hi"), AIMessage(role="assistant", content="hello")],
        system="be terse",
    )
    assert msgs[0] == {"role": "system", "content": "be terse"}
    assert msgs[1] == {"role": "user", "content": [{"type": "text", "text": "hi"}]}
    assert msgs[2] == {"role": "assistant", "content": "hello"}


def test_parse_line_text_delta_and_usage():
    line = ('data: {"choices":[{"delta":{"content":"Gran"}}],'
            '"usage":{"prompt_tokens":7,"completion_tokens":2}}')
    chunks = _parse_line(line)
    assert chunks[0] == TextDelta("Gran")
    assert chunks[1] == Usage(input_tokens=7, output_tokens=2)


def test_parse_line_ignores_noise():
    assert _parse_line("") == []
    assert _parse_line("event: message") == []
    assert _parse_line("data: [DONE]") == []
    assert _parse_line("data: not-json") == []
    assert _parse_line('data: {"choices":[{"delta":{}}]}') == []


def test_missing_key_is_an_authentication_error():
    p = WatsonxProvider(ProviderConfig(provider_type="watsonx"))
    with pytest.raises(ProviderError) as err:
        p._key()
    assert err.value.category == "authentication"
