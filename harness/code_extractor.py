"""LLM 応答から Python コードブロックを抽出する。"""
from __future__ import annotations

import re

# ```python ... ``` または ``` ... ``` を検出
_FENCED = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL)


def extract_code(text: str) -> str:
    """応答文字列から最大の Python コードブロックを返す。

    フェンス付きブロックがなければテキスト全体を返す（フェンスを忘れた場合への配慮）。
    """
    matches = _FENCED.findall(text)
    if not matches:
        return text.strip()
    # 最も長いブロックを採用
    return max(matches, key=len).strip()
