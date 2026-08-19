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
    c = make_client("ollama:llama3.1:8b")
    assert isinstance(c, OpenAICompatClient)
    # モデル名中のコロンが保持される（split は maxsplit=1）
    assert c.model_id == "llama3.1:8b"
    assert c.base_url == "http://localhost:11434/v1"


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
