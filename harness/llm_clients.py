"""LLM プロバイダ統一インターフェース。

Provider:
  - "mock": API キー不要。タスクの mock_correct_code or mock_wrong_code を返す
  - "openai": OPENAI_API_KEY が必要
  - "anthropic": ANTHROPIC_API_KEY が必要
  - "google": GOOGLE_API_KEY が必要
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class Generation:
    raw_text: str
    tokens_in: int = 0
    tokens_out: int = 0
    elapsed_sec: float = 0.0
    model_id: str = ""
    error: str = ""
    timeout_flag: bool = False


def _is_timeout_error(error: Exception | str) -> bool:
    name = type(error).__name__.lower() if isinstance(error, Exception) else ""
    message = str(error).lower()
    return "timeout" in name or "timed out" in message or "timeout" in message


def _read_system_prompt() -> str:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, "prompts", "system.txt"), encoding="utf-8") as f:
        return f.read()


SYSTEM_PROMPT = _read_system_prompt()


# ---------- Mock ----------


class MockClient:
    """API キー不要。task に応じた canned 回答を返す。

    seed が偶数なら correct、奇数なら wrong を返す（テストで両ケース確認）。
    """

    def __init__(self, model_id: str = "mock-correct"):
        # "mock-correct" or "mock-wrong" or "mock-mixed"
        self.model_id = model_id

    def generate(
        self,
        user_prompt: str,
        seed: int,
        temperature: float = 0.7,
        task=None,
    ) -> Generation:
        # task は MockClient の場合のみ使用（canned ロジックのため）
        if task is None:
            return Generation(
                raw_text="```python\n# mock has no task context\n```",
                model_id=self.model_id,
                error="no_task_for_mock",
            )

        if self.model_id == "mock-correct":
            code = task.mock_correct_code
        elif self.model_id == "mock-wrong":
            code = task.mock_wrong_code
        elif self.model_id == "mock-mixed":
            code = task.mock_correct_code if seed % 2 == 0 else task.mock_wrong_code
        else:
            code = task.mock_correct_code

        text = f"```python\n{code}```"
        return Generation(
            raw_text=text,
            tokens_in=len(user_prompt) // 4,
            tokens_out=len(code) // 4,
            elapsed_sec=0.0,
            model_id=self.model_id,
        )


# ---------- OpenAI ----------


class OpenAIClient:
    def __init__(self, model_id: str):
        from openai import OpenAI

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        self._client = OpenAI(api_key=api_key)
        self.model_id = model_id

    def generate(
        self, user_prompt: str, seed: int, temperature: float = 0.7, task=None
    ) -> Generation:
        t0 = time.time()
        try:
            resp = self._client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                seed=seed,
            )
            text = resp.choices[0].message.content or ""
            usage = resp.usage
            return Generation(
                raw_text=text,
                tokens_in=usage.prompt_tokens if usage else 0,
                tokens_out=usage.completion_tokens if usage else 0,
                elapsed_sec=time.time() - t0,
                model_id=self.model_id,
            )
        except Exception as e:
            return Generation(
                raw_text="",
                elapsed_sec=time.time() - t0,
                model_id=self.model_id,
                error=f"{type(e).__name__}: {e}",
                timeout_flag=_is_timeout_error(e),
            )


# ---------- Anthropic ----------


class AnthropicClient:
    def __init__(self, model_id: str):
        import anthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        self._client = anthropic.Anthropic(api_key=api_key)
        self.model_id = model_id

    def generate(
        self, user_prompt: str, seed: int, temperature: float = 0.7, task=None
    ) -> Generation:
        # Anthropic API は seed をサポートしないため、temperature と再現用 metadata で代用
        t0 = time.time()
        try:
            resp = self._client.messages.create(
                model=self.model_id,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                temperature=temperature,
                messages=[{"role": "user", "content": user_prompt}],
                metadata={"user_id": f"qiskit-eval-seed-{seed}"},
            )
            text = "".join(
                block.text for block in resp.content if hasattr(block, "text")
            )
            return Generation(
                raw_text=text,
                tokens_in=resp.usage.input_tokens,
                tokens_out=resp.usage.output_tokens,
                elapsed_sec=time.time() - t0,
                model_id=self.model_id,
            )
        except Exception as e:
            return Generation(
                raw_text="",
                elapsed_sec=time.time() - t0,
                model_id=self.model_id,
                error=f"{type(e).__name__}: {e}",
                timeout_flag=_is_timeout_error(e),
            )


# ---------- Google ----------


class GoogleClient:
    def __init__(self, model_id: str):
        import google.generativeai as genai

        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY not set")
        genai.configure(api_key=api_key)
        self._genai = genai
        self.model_id = model_id

    def generate(
        self, user_prompt: str, seed: int, temperature: float = 0.7, task=None
    ) -> Generation:
        t0 = time.time()
        try:
            model = self._genai.GenerativeModel(
                model_name=self.model_id,
                system_instruction=SYSTEM_PROMPT,
            )
            cfg = self._genai.types.GenerationConfig(temperature=temperature)
            resp = model.generate_content(user_prompt, generation_config=cfg)
            text = resp.text or ""
            usage = getattr(resp, "usage_metadata", None)
            return Generation(
                raw_text=text,
                tokens_in=getattr(usage, "prompt_token_count", 0) if usage else 0,
                tokens_out=getattr(usage, "candidates_token_count", 0) if usage else 0,
                elapsed_sec=time.time() - t0,
                model_id=self.model_id,
            )
        except Exception as e:
            return Generation(
                raw_text="",
                elapsed_sec=time.time() - t0,
                model_id=self.model_id,
                error=f"{type(e).__name__}: {e}",
                timeout_flag=_is_timeout_error(e),
            )


# ---------- Claude Code CLI (サブスクリプション経由) ----------


class ClaudeCLIClient:
    """ログイン済み Claude Code (`claude -p`) を生成バックエンドにする。

    API キー (ANTHROPIC_API_KEY) ではなく Claude Code のサブスクリプション認証を
    使うため、API 課金が発生しない。髙栁の experiments/tools/generate.py と同じ方式。

    注意:
    - `claude -p` は temperature/seed を公開していないため、本クライアントでは
      これらは無視される（各呼び出しは独立セッション = 新規会話）。再現性は
      metadata の seed と固定モデル ID で担保する。
    - system プロンプトは --append-system-prompt で Claude Code の既定 system に
      追記する形で注入する。
    - tokens_in/out は --output-format json の usage から取得する。
    """

    def __init__(self, model_id: str):
        import shutil

        if shutil.which("claude") is None:
            raise RuntimeError("`claude` CLI not found on PATH")
        self.model_id = model_id

    def generate(
        self, user_prompt: str, seed: int, temperature: float = 0.7, task=None
    ) -> Generation:
        import json
        import subprocess

        cmd = [
            "claude",
            "-p",
            "--model",
            self.model_id,
            "--append-system-prompt",
            SYSTEM_PROMPT,
            "--output-format",
            "json",
        ]
        t0 = time.time()
        try:
            proc = subprocess.run(
                cmd,
                input=user_prompt,
                capture_output=True,
                text=True,
                timeout=300,
            )
            elapsed = time.time() - t0
            if proc.returncode != 0:
                return Generation(
                    raw_text="",
                    elapsed_sec=elapsed,
                    model_id=self.model_id,
                    error=f"claude_cli_exit_{proc.returncode}: {proc.stderr.strip()[:200]}",
                )
            data = json.loads(proc.stdout)
            if data.get("is_error"):
                return Generation(
                    raw_text="",
                    elapsed_sec=elapsed,
                    model_id=self.model_id,
                    error=f"claude_cli_error: {str(data.get('result'))[:200]}",
                )
            usage = data.get("usage") or {}
            return Generation(
                raw_text=data.get("result") or "",
                tokens_in=usage.get("input_tokens", 0),
                tokens_out=usage.get("output_tokens", 0),
                elapsed_sec=elapsed,
                model_id=self.model_id,
            )
        except Exception as e:
            return Generation(
                raw_text="",
                elapsed_sec=time.time() - t0,
                model_id=self.model_id,
                error=f"{type(e).__name__}: {e}",
                timeout_flag=_is_timeout_error(e),
            )


# ---------- ローカル LLM (OpenAI 互換エンドポイント) ----------


# プロバイダごとの既定エンドポイント / ダミーキー。
# Ollama・vLLM・LM Studio・llama.cpp の server はいずれも OpenAI 互換の
# /v1/chat/completions を公開するため、openai パッケージの base_url 差し替えだけで叩ける。
_LOCAL_DEFAULTS = {
    # ollama serve の既定ポート。`ollama pull <model>` 済みのモデル名をそのまま指定する
    "ollama": {
        "base_url_env": "OLLAMA_BASE_URL",
        "base_url_default": "http://127.0.0.1:11434/v1",
        "api_key_env": "OLLAMA_API_KEY",
        "api_key_default": "ollama",  # ローカルなので任意の非空文字列でよい
    },
    # vLLM (--api-server) / LM Studio / llama.cpp server などの汎用ローカル
    "local": {
        "base_url_env": "LOCAL_LLM_BASE_URL",
        "base_url_default": "http://localhost:8000/v1",
        "api_key_env": "LOCAL_LLM_API_KEY",
        "api_key_default": "sk-no-key",
    },
}


class OpenAICompatClient:
    """OpenAI 互換エンドポイントを叩く汎用クライアント（ローカル LLM 用）。

    openai パッケージの `base_url` をローカルサーバに向けるだけで、Ollama・vLLM・
    LM Studio・llama.cpp server を同一インターフェースで扱える。API 課金は発生せず、
    生成はすべてローカルマシン上で完結する。

    再現性:
    - ローカルサーバの多くは `seed` を尊重するため、まず seed 付きで要求する。
      サーバが seed を受け付けない場合は seed なしで一度だけリトライする。
    """

    def __init__(self, model_id: str, base_url: str, api_key: str):
        from openai import OpenAI

        self._client = OpenAI(base_url=base_url, api_key=api_key)
        self.model_id = model_id
        self.base_url = base_url

    def _create(self, user_prompt: str, temperature: float, seed: Optional[int]):
        kwargs = dict(
            model=self.model_id,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
        )
        if seed is not None:
            kwargs["seed"] = seed
        return self._client.chat.completions.create(**kwargs)

    def generate(
        self, user_prompt: str, seed: int, temperature: float = 0.7, task=None
    ) -> Generation:
        t0 = time.time()
        try:
            try:
                resp = self._create(user_prompt, temperature, seed)
            except Exception as first_error:
                if _is_timeout_error(first_error):
                    raise
                # seed 非対応サーバ向けに seed を外して 1 回だけリトライ
                resp = self._create(user_prompt, temperature, None)
            text = resp.choices[0].message.content or ""
            usage = getattr(resp, "usage", None)
            return Generation(
                raw_text=text,
                tokens_in=getattr(usage, "prompt_tokens", 0) if usage else 0,
                tokens_out=getattr(usage, "completion_tokens", 0) if usage else 0,
                elapsed_sec=time.time() - t0,
                model_id=self.model_id,
            )
        except Exception as e:
            return Generation(
                raw_text="",
                elapsed_sec=time.time() - t0,
                model_id=self.model_id,
                error=f"{type(e).__name__}: {e}",
                timeout_flag=_is_timeout_error(e),
            )


def _normalize_base_url(url: str) -> str:
    """OpenAI 互換エンドポイントは `/v1` 配下にあるため末尾を補正する。

    ollama 系の環境変数 (OLLAMA_BASE_URL / OLLAMA_HOST) はホスト root
    (例: http://localhost:11434) を指すのが慣例で `/v1` を含まないことが多い。
    その場合に `/chat/completions` が 404 になるのを防ぐ。
    """
    url = url.rstrip("/")
    if not url.endswith("/v1"):
        url += "/v1"
    return url


def _make_local_client(provider: str, model_id: str) -> OpenAICompatClient:
    cfg = _LOCAL_DEFAULTS[provider]
    # OLLAMA_BASE_URL is the harness-specific override. Also accept Ollama's
    # standard OLLAMA_HOST variable so shared/local Ollama setup instructions
    # route generation to the same server selected by the user.
    base_url = os.environ.get(cfg["base_url_env"])
    if provider == "ollama" and not base_url:
        base_url = os.environ.get("OLLAMA_HOST")
    base_url = _normalize_base_url(
        base_url or cfg["base_url_default"]
    )
    api_key = os.environ.get(cfg["api_key_env"], cfg["api_key_default"])
    return OpenAICompatClient(model_id, base_url=base_url, api_key=api_key)


# ---------- Factory ----------


def make_client(model_spec: str):
    """model_spec の例:
    - "mock-correct", "mock-wrong", "mock-mixed"
    - "openai:gpt-4o", "openai:gpt-5"
    - "anthropic:claude-opus-4-7"
    - "google:gemini-2.5-pro"
    - "claude-cli:claude-haiku-4-5"  (サブスクリプション経由・API キー不要)
    - "ollama:llama3.1:8b"           (ローカル Ollama・API 課金なし)
    - "local:Qwen2.5-Coder-7B"       (汎用 OpenAI 互換ローカルサーバ: vLLM 等)
    """
    if model_spec.startswith("mock"):
        return MockClient(model_id=model_spec)
    if ":" not in model_spec:
        raise ValueError(f"model_spec must be 'provider:model' (got: {model_spec})")
    provider, model_id = model_spec.split(":", 1)
    if provider == "openai":
        return OpenAIClient(model_id)
    if provider == "anthropic":
        return AnthropicClient(model_id)
    if provider == "google":
        return GoogleClient(model_id)
    if provider == "claude-cli":
        return ClaudeCLIClient(model_id)
    if provider in _LOCAL_DEFAULTS:
        return _make_local_client(provider, model_id)
    raise ValueError(f"Unknown provider: {provider}")
