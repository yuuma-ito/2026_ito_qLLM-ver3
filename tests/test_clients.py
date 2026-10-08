"""llm_clients の Factory / ローカル LLM クライアント構築の自己テスト。

ネットワークやローカルサーバ起動は不要（クライアントの構築のみ検証）。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

try:
    import httpx2 as httpx
except ImportError:
    import httpx

from harness.llm_clients import MockClient, OpenAICompatClient, make_client


def test_make_client_mock():
    c = make_client("mock-correct")
    assert isinstance(c, MockClient)


def test_make_client_requires_provider_prefix():
    with pytest.raises(ValueError):
        make_client("gpt-4o")  # provider なし


def test_make_client_unknown_provider():
    with pytest.raises(ValueError):
        make_client("foo:bar")


def test_ollama_uses_default_base_url(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    c = make_client("ollama:llama3.1:8b")
    assert isinstance(c, OpenAICompatClient)
    # モデル名中のコロンが保持される（split は maxsplit=1）
    assert c.model_id == "llama3.1:8b"
    assert c.base_url == "http://127.0.0.1:11434/v1"


def test_shared_ollama_disables_thinking_and_bounds_output(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:11435")
    client = make_client("ollama:qwen3.5:4b")
    requests = []
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kwargs: requests.append(kwargs)
    )))
    client._create("test", 0.7, 0)
    client._create("test", 0.7, None)
    assert client.base_url == "http://127.0.0.1:11435/v1"
    assert all(r["reasoning_effort"] == "none" and r["max_tokens"] == 1024 for r in requests)
    assert requests[0]["seed"] == 0
    assert "seed" not in requests[1]


def test_ollama_base_url_normalized_to_v1(monkeypatch):
    # ホスト root だけ指定する慣例 (OLLAMA_BASE_URL=...:11434) でも /v1 を補う
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    c = make_client("ollama:llama3.1:8b")
    assert c.base_url == "http://localhost:11434/v1"


def test_local_uses_default_base_url(monkeypatch):
    monkeypatch.delenv("LOCAL_LLM_BASE_URL", raising=False)
    c = make_client("local:Qwen2.5-Coder-7B")
    assert isinstance(c, OpenAICompatClient)
    assert c.model_id == "Qwen2.5-Coder-7B"
    assert c.base_url == "http://localhost:8000/v1"


def test_local_base_url_env_override(monkeypatch):
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://192.168.0.2:9000/v1")
    c = make_client("local:my-model")
    assert c.base_url == "http://192.168.0.2:9000/v1"


def compat_response():
    from types import SimpleNamespace
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="code"))], usage=None)


def test_ollama_recovers_connection_with_same_seed_and_records_retries(monkeypatch):
    from openai import APIConnectionError
    from harness import llm_clients
    client = make_client("ollama:test")
    calls, waits = [], []
    def create(prompt, temperature, seed):
        calls.append((prompt, temperature, seed))
        if len(calls) < 3:
            raise APIConnectionError(request=httpx.Request("POST", "http://localhost/v1"))
        return compat_response()
    monkeypatch.setattr(client, "_create", create)
    monkeypatch.setattr(llm_clients.time, "sleep", waits.append)
    result = client.generate("prompt", 42, .3)
    assert result.error == ""
    assert result.raw_text == "code"
    assert result.connection_retries == 2
    assert waits == [5, 10]
    assert calls == [("prompt", .3, 42)] * 3


def test_ollama_bounds_connection_retries_and_preserves_failure(monkeypatch):
    from openai import APIConnectionError
    from harness import llm_clients
    client = make_client("ollama:test")
    calls, waits = [], []
    def fail(prompt, temperature, seed):
        calls.append(seed)
        raise APIConnectionError(request=httpx.Request("POST", "http://localhost/v1"))
    monkeypatch.setattr(client, "_create", fail)
    monkeypatch.setattr(llm_clients.time, "sleep", waits.append)
    result = client.generate("prompt", 42)
    assert "APIConnectionError" in result.error
    assert not result.timeout_flag
    assert result.connection_retries == 5
    assert calls == [42] * 6
    assert waits == [5, 10, 20, 30, 30]


@pytest.mark.parametrize("failure", ["timeout", "unauthorized", "bad_request"])
def test_other_errors_do_not_trigger_connection_retry_or_drop_seed(monkeypatch, failure):
    from openai import APITimeoutError, AuthenticationError, BadRequestError
    from harness import llm_clients
    client = make_client("ollama:test")
    request = httpx.Request("POST", "http://localhost/v1")
    error = APITimeoutError(request=request) if failure == "timeout" else (
        AuthenticationError("unauthorized", response=httpx.Response(401, request=request), body=None)
        if failure == "unauthorized" else
        BadRequestError("invalid model", response=httpx.Response(400, request=request), body=None))
    calls = []
    def fail(prompt, temperature, seed):
        calls.append(seed)
        raise error
    monkeypatch.setattr(client, "_create", fail)
    monkeypatch.setattr(llm_clients.time, "sleep", lambda *_: pytest.fail("Unexpected retry"))
    result = client.generate("prompt", 42)
    assert result.error
    assert result.timeout_flag == (failure == "timeout")
    assert result.connection_retries == 0
    assert calls == [42]


def test_seed_fallback_only_for_explicit_unsupported_seed(monkeypatch):
    from openai import BadRequestError
    client = make_client("local:test")
    seeds = []
    def create(prompt, temperature, seed):
        seeds.append(seed)
        if seed is not None:
            raise BadRequestError("seed is not supported", response=httpx.Response(
                400, request=httpx.Request("POST", "http://localhost/v1")), body=None)
        return compat_response()
    monkeypatch.setattr(client, "_create", create)
    assert client.generate("prompt", 42).error == ""
    assert seeds == [42, None]
