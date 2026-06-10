from __future__ import annotations

import json
from typing import Any

from knowledge_base.llm_client import call_llm


def test_token_plan_endpoint_accepts_configured_env_key(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def read(self) -> bytes:
            return json.dumps(
                {"choices": [{"message": {"content": "ok"}}]},
                ensure_ascii=False,
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv("RADAGENT_MODEL_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")
    monkeypatch.setenv("RADAGENT_MODEL_PRO", "mimo-v2.5-pro")
    monkeypatch.setenv("RADAGENT_API_KEY", "plain-configured-key")
    monkeypatch.delenv("RADAGENT_PRO_API_KEY_ENV", raising=False)
    monkeypatch.delenv("TEST_RADAGENT_KEY", raising=False)
    monkeypatch.setattr("knowledge_base.llm_client.urllib.request.urlopen", fake_urlopen)

    result = call_llm(
        [{"role": "user", "content": "ping"}],
        max_tokens=16,
        model_tier="pro",
        enable_thinking=False,
        timeout=12,
    )

    assert result == "ok"
    assert captured["url"] == "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"
    assert captured["headers"]["Api-key"] == "plain-configured-key"
    assert "Authorization" not in captured["headers"]
    assert captured["payload"]["model"] == "mimo-v2.5-pro"
    assert captured["payload"]["max_completion_tokens"] == 16
    assert captured["payload"]["thinking"] == {"type": "disabled"}
    assert captured["timeout"] == 12


def test_knowledge_base_client_uses_shared_default_model_config(monkeypatch) -> None:
    from agent_core.config.environment import DEFAULT_MODEL_BASE_URL, DEFAULT_MODEL_PRO
    from knowledge_base import llm_client

    monkeypatch.delenv("RADAGENT_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("RADAGENT_PRO_BASE_URL", raising=False)
    monkeypatch.delenv("RADAGENT_MODEL_PRO", raising=False)

    assert llm_client._base_url_for_tier("pro") == DEFAULT_MODEL_BASE_URL
    assert llm_client._model_for_tier("pro") == DEFAULT_MODEL_PRO
