"""ベースライン実行: 全モデル × 全タスク × 全 seed を JSONL に追記する。

使用例:
  python -m scripts.run_baseline --mock --seeds 1 --out results/mock.jsonl
  python -m scripts.run_baseline --models openai:gpt-4o,anthropic:claude-opus-4-7 \\
      --seeds 10 --out results/baseline_v1.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

from dotenv import load_dotenv

from harness.llm_clients import make_client
from harness.runner import run_one, run_refine
from tasks import all_tasks, get_task


def main() -> int:
    parser = argparse.ArgumentParser(description="Qiskit LLM eval baseline runner")
    parser.add_argument(
        "--models",
        default="",
        help="Comma-separated model specs (e.g. openai:gpt-4o,anthropic:claude-opus-4-7)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock-mixed (correct on even seeds, wrong on odd) for animation-free run",
    )
    parser.add_argument("--seeds", type=int, default=1, help="Number of seeds (0..N-1)")
    parser.add_argument(
        "--tasks",
        default="",
        help="Comma-separated task IDs to run (default: all)",
    )
    parser.add_argument("--out", required=True, help="Output JSONL path")
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument(
        "--refine",
        action="store_true",
        help="Self-Refine モード（生成→評価→失敗時フィードバック再生成のループ）",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=3,
        help="Self-Refine の最大ラウンド数（--refine 時のみ有効、既定 3）",
    )
    args = parser.parse_args()

    load_dotenv()

    # モデル決定
    if args.mock:
        model_specs = ["mock-mixed"]
    else:
        if not args.models:
            sys.exit("ERROR: --models is required (or use --mock)")
        model_specs = [m.strip() for m in args.models.split(",") if m.strip()]

    # タスク決定
    if args.tasks:
        task_ids = [t.strip() for t in args.tasks.split(",") if t.strip()]
        tasks = [get_task(tid) for tid in task_ids]
    else:
        tasks = all_tasks()

    # 出力先準備
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)

    mode = f"refine(max_rounds={args.max_rounds})" if args.refine else "baseline"
    print(
        f"Mode: {mode}\n"
        f"Models: {model_specs}\n"
        f"Tasks: {[t.id for t in tasks]}\n"
        f"Seeds: 0..{args.seeds-1}\n"
        f"Output: {args.out}\n"
    )

    n_total = len(model_specs) * len(tasks) * args.seeds
    n_done = 0
    t_start = time.time()

    with open(args.out, "a", encoding="utf-8") as f:
        for spec in model_specs:
            try:
                client = make_client(spec)
            except Exception as e:
                print(f"  ERROR: cannot init {spec}: {e}", file=sys.stderr)
                continue
            for task in tasks:
                for seed in range(args.seeds):
                    if args.refine:
                        rec = run_refine(
                            client,
                            task,
                            seed,
                            max_rounds=args.max_rounds,
                            temperature=args.temperature,
                        )
                    else:
                        rec = run_one(
                            client, task, seed, temperature=args.temperature
                        )
                    f.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")
                    f.flush()
                    n_done += 1
                    flag = "OK" if rec.L2 else f"L2x[{rec.error_category}]"
                    rinfo = (
                        f" rounds={rec.n_rounds} first_ok={rec.first_success_round}"
                        if args.refine
                        else ""
                    )
                    print(
                        f"  [{n_done}/{n_total}] {spec} {task.id} seed={seed} "
                        f"L0={int(rec.L0)} L1={int(rec.L1)} L2={int(rec.L2)} "
                        f"L3={int(rec.L3)} d={rec.L2_distance:.4f}{rinfo} {flag}"
                    )

    elapsed = time.time() - t_start
    print(f"\nDone. {n_done} samples in {elapsed:.1f}s.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
