"""JSONL ベースライン結果を集計してレポート出力する。

使用例:
  python -m scripts.analyze results/baseline_v1.jsonl
  python -m scripts.analyze results/baseline_v1.jsonl --markdown > report.md
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict

from harness.failure_metadata import normalize_record


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate baseline JSONL results")
    parser.add_argument("path", help="Input JSONL path")
    parser.add_argument(
        "--markdown", action="store_true", help="Output Markdown table"
    )
    args = parser.parse_args()

    # (mode, model, task) で集計。mode 欠落の旧形式は "baseline" 扱い。
    by_key: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    error_counter: dict[str, int] = defaultdict(int)
    seen_refine = False

    with open(args.path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = normalize_record(json.loads(line))
            mode = rec.get("mode", "baseline")
            if mode == "refine":
                seen_refine = True
            by_key[(mode, rec["model"], rec["task_id"])].append(rec)
            if not rec["L2"]:
                error_counter[rec["error_category"]] += 1

    # 集計
    rows = []
    for (mode, model, task_id), recs in sorted(by_key.items()):
        n = len(recs)
        l0 = sum(1 for r in recs if r["L0"]) / n
        l1 = sum(1 for r in recs if r["L1"]) / n
        l2 = sum(1 for r in recs if r["L2"]) / n
        l3 = sum(1 for r in recs if r["L3"]) / n
        # L1 が通った中の平均 L2 距離
        d_vals = [r["L2_distance"] for r in recs if r["L1"]]
        d_avg = sum(d_vals) / len(d_vals) if d_vals else float("nan")
        # refine 用: 平均ラウンド数、成功例の平均到達ラウンド
        rounds_avg = sum(r.get("n_rounds", 1) for r in recs) / n
        ok_first = [
            r["first_success_round"]
            for r in recs
            if r.get("first_success_round", -1) >= 0
        ]
        first_ok_avg = sum(ok_first) / len(ok_first) if ok_first else float("nan")
        rows.append(
            dict(
                mode=mode,
                model=model,
                task=task_id,
                n=n,
                L0=l0,
                L1=l1,
                L2=l2,
                L3=l3,
                d_avg=d_avg,
                rounds_avg=rounds_avg,
                first_ok_avg=first_ok_avg,
            )
        )

    def _fmt(x: float, p: int = 3) -> str:
        return "nan" if x != x else f"{x:.{p}f}"

    # 出力
    if args.markdown:
        cols = "| mode | model | task | n | L0 | L1 | L2 | L3 | avg L2 dist |"
        sep = "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"
        if seen_refine:
            cols += " avg rounds | avg first-ok |"
            sep += " --- | --- |"
        print(cols)
        print(sep)
        for r in rows:
            line = (
                f"| {r['mode']} | {r['model']} | {r['task']} | {r['n']} | "
                f"{r['L0']:.0%} | {r['L1']:.0%} | {r['L2']:.0%} | {r['L3']:.0%} | "
                f"{_fmt(r['d_avg'])} |"
            )
            if seen_refine:
                line += f" {_fmt(r['rounds_avg'], 2)} | {_fmt(r['first_ok_avg'], 2)} |"
            print(line)
        if seen_refine:
            print()
            _print_mode_summary_md(rows)
        print()
        print("## 失敗カテゴリ")
        print()
        if error_counter:
            print("| category | count |")
            print("| --- | --- |")
            for cat, cnt in sorted(error_counter.items(), key=lambda x: -x[1]):
                print(f"| {cat} | {cnt} |")
        else:
            print("(no failures)")
    else:
        for r in rows:
            extra = (
                f" rounds={_fmt(r['rounds_avg'], 2)} first_ok={_fmt(r['first_ok_avg'], 2)}"
                if seen_refine
                else ""
            )
            print(
                f"{r['mode']:8} {r['model']:24} {r['task']:25} n={r['n']:3} "
                f"L0={r['L0']:.0%} L1={r['L1']:.0%} L2={r['L2']:.0%} "
                f"L3={r['L3']:.0%} d={_fmt(r['d_avg'])}{extra}"
            )
        if seen_refine:
            print()
            _print_mode_summary_text(rows)
        print("\n失敗カテゴリ:")
        for cat, cnt in sorted(error_counter.items(), key=lambda x: -x[1]):
            print(f"  {cat}: {cnt}")

    return 0


def _mode_l2(rows: list[dict]) -> dict[str, float]:
    """mode ごとの全体 L2 成功率（タスク横断、サンプル数重み付け）。"""
    agg: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        agg[r["mode"]].extend([r["L2"]] * r["n"])
    return {m: (sum(v) / len(v) if v else float("nan")) for m, v in agg.items()}


def _print_mode_summary_md(rows: list[dict]) -> None:
    print("## モード別 全体 L2 成功率")
    print()
    overall = _mode_l2(rows)
    print("| mode | overall L2 |")
    print("| --- | --- |")
    for m in sorted(overall):
        print(f"| {m} | {overall[m]:.1%} |")
    if "baseline" in overall and "refine" in overall:
        gain = overall["refine"] - overall["baseline"]
        print(f"| **refine − baseline** | **{gain:+.1%}** |")


def _print_mode_summary_text(rows: list[dict]) -> None:
    print("モード別 全体 L2 成功率:")
    overall = _mode_l2(rows)
    for m in sorted(overall):
        print(f"  {m}: {overall[m]:.1%}")
    if "baseline" in overall and "refine" in overall:
        print(f"  refine − baseline: {overall['refine'] - overall['baseline']:+.1%}")


if __name__ == "__main__":
    raise SystemExit(main())
