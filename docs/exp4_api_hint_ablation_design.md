# exp4 実験設計: API ヒント ablation（「API の新しさ」と「推論能力」の分離）

作成 2026-07-01。exp3（`findings.md`「gemma3:4b はなぜ 0% か」）の続き。

## 0. 動機 ＋ exp3 で判明した交絡（本設計の出発点・最重要）

exp3 で gemma3:4b は全タスク L2=0%、最大要因は旧 Qiskit API（`Aer`/`execute`）の import 失敗だった。
しかし調査の結果、**exp1–3 の gemma と coder は別ランナー・別プロンプトで走っていた**ことが判明:

| モデル | ランナー | タスク命名 | プロンプトの API ヒント |
|---|---|---|---|
| gemma3:4b | 本体 harness `run_baseline.py` | `T3a_DJ_constant` 等 | **無し**（`tasks/*.py` prompt_text ＋ system.txt は "version 2.x" 言及のみ） |
| qwen2.5-coder-7b-32k | `run_local_coder.py` | `T3_DJ_balanced` 等 | **有り**（"Use only from qiskit_aer import AerSimulator; Do NOT use deprecated qiskit.Aer or qiskit.execute"） |

→ **gemma 0% は「モデル能力」だけでなく「ヒント無しプロンプト」と交絡**している。
exp4 はまずこの交絡を解き、API ヒントの純効果を測る。

## 1. リサーチクエスチョンと仮説

- **RQ**: gemma の失敗は「API 知識の古さ（API ドリフト）」か「回路ロジックの推論能力不足」か。ヒントで分離できるか。
- **H1**: API ヒント注入で gemma の import 失敗率が大幅に減り、L0 通過率が上がる（＝失敗の主因は API の古さ）。
- **H2**: L0 が上がっても L2 はあまり上がらない（＝回路ロジックの推論が別のボトルネック）。
- **H3**: 穴埋めテンプレート（import/シグネチャ固定）で import/signature 失敗クラスが消え、**純粋な回路ロジック能力**（L2 | L0通過）を測れる。
- **H4**: capable モデル（coder/32b）はヒント無しでも高く、ヒントの限界効用は小さい（天井効果）。

## 2. 要因計画

2 要因 ＋ 統制:
- **要因 A: HINT** ∈ {`H0` なし, `H1` system 契約, `H2` H1＋few-shot 正例, `H3` 穴埋めテンプレート}
- **要因 B: MODEL** ∈ {`gemma3:4b`（主対象）, `qwen2.5-coder-7b`（天井・対照）}（任意で `qwen2.5:32b`）
- 各セル: **MODE** ∈ {baseline, refine} × 10 タスク × **n=10 seeds**

統制（交絡除去・最重要）:
- **単一ランナー・単一タスク定義に統一**。本体 harness（`tasks/` ＋ `run_baseline.py` ＋ `harness/`）を正とし、`run_local_coder.py` の内蔵タスクは使わない（exp3 の交絡の再発防止）。
- 同一 Qiskit 2.x 環境・同一 seeds・同一 temperature。
- **HINT は system プロンプトのみで差し替え**、task prompt は固定 → ヒントの純効果を分離（H3 のみ task 末尾にテンプレートを付加）。

## 3. ヒント文面（具体・そのまま使える）

**H0**: 現行 `prompts/system.txt` のまま（"qiskit (version 2.x)" の言及のみ）。

**H1 — system 契約（version ＋ 記号レベルの do/don't）**:
```
Environment: Qiskit 2.x with qiskit-aer. Follow these API rules exactly:
- Import only what you use. For simulation use: `from qiskit_aer import AerSimulator`.
- DO NOT use removed APIs: `from qiskit import Aer`, `qiskit.execute`, `qiskit.algorithms` (removed in Qiskit 1.0).
- Gate methods: use `cx` (not `cnot`), `ccx` (not `ccnot`).
- Define exactly `def build_circuit() -> QuantumCircuit:` with NO arguments.
- Do NOT add measurements inside build_circuit.
- Output only one ```python fenced block, no prose.
```

**H2 = H1 ＋ 最小正例（few-shot 1 個・非リーク）**:
```
Example of the required modern idiom (structure only, not the answer):
```python
from qiskit import QuantumCircuit
def build_circuit() -> QuantumCircuit:
    qc = QuantumCircuit(1)
    qc.h(0)
    return qc
```
```
※ 正例はどのタスクの答えにもならない自明回路にして**非リーク**を厳守。

**H3 — 穴埋めテンプレート（最も統制的）**: import 行と def 行をこちらが与え、本体だけ生成させる。task prompt 末尾に付加:
```
Complete ONLY the body. Return the whole file unchanged except the body:
```python
from qiskit import QuantumCircuit
def build_circuit() -> QuantumCircuit:
    # YOUR CODE HERE
    return qc
```
```
→ import 失敗・signature 違反クラスを**構造的に排除**し、回路ロジック能力だけを残す。

## 4. 必要なコード変更（最小）

1. `run_baseline.py` / `make_client` に **`--hint {h0,h1,h2,h3}`**（または `--system-prompt-file PATH`）を追加。現状 `SYSTEM_PROMPT` は import 時に固定なので、**client 生成時に system プロンプトを渡せる**よう小改修。
2. H3 用に「テンプレート本体差し込み」: task prompt にテンプレを付加（`extract_code` は既存のままテンプレ全体を拾える）。
3. （任意条件 H1+R）refine feedback 強化: 生エラーに修正規則を添える（"`Aer`/`execute` were removed → use `qiskit_aer.AerSimulator`"）。
4. **データ品質バグの修正（必須）**: exp3 gemma で観測した「1 ラウンド＝5 重複・ラウンド欠落」を出さないよう、seed ループと JSONL 書き込みを点検（**1 (task,seed) = 1 行**を保証）。`results/local_data_quality.md` の診断を回帰テストに使う。

## 5. 指標と分析

- **主要 DV**: L2 成功率（task × model × HINT × MODE）。
- **機構 DV（最重要）**: **import 失敗率**・L0 通過率の HINT 依存。H0→H1 で import 失敗が崩れるか。
- **失敗カテゴリ遷移**: import / build_error（signature・hallucination） / wrong_output の構成比変化。
- **条件付き L2**: `L2 | L0通過`（コードが動いた中での正答率）＝純粋な回路ロジック能力。H3 で特に重要。
- **refine の限界効用**: HINT × MODE 交互作用（ヒントで baseline が上がると refine の伸び代は縮むか）。
- 効果量 ＋ ブートストラップ CI（n=10/セル）。

## 6. サンプル設計と実行

- 規模: 主対象 gemma は全 4 HINT、対照 coder は {H0, H1, H3} の 3 水準で天井確認に十分。
- 概算: gemma {4 HINT}×{baseline,refine}×10task×10seed = 800、coder ~600 → **計 ~1400 生成**（gemma ~30s/gen, coder ~20s, refine は ×~2）。既存「8h 夜間連鎖」方式で回す。
- コマンド（改修後の想定）:
  ```bash
  for H in h0 h1 h2 h3; do
    python -m scripts.run_baseline --models ollama:gemma3:4b --seeds 10 --hint $H --out results/exp4_${H}.jsonl
    python -m scripts.run_baseline --models ollama:gemma3:4b --seeds 10 --hint $H --refine --max-rounds 3 --out results/exp4_${H}.jsonl
  done
  python -m scripts.analyze results/exp4_*.jsonl --markdown > results/exp4_report.md
  ```

## 7. 期待結果と解釈（決定表）

| 観測 | 解釈 |
|---|---|
| H1 で import 失敗が激減・L0↑・L2 も↑ | gemma の失敗は主に **API の新しさ**。ヒントで実用域に乗る。 |
| H1 で L0↑ だが L2 横ばい | API はヒントで解決するが、**回路ロジックの推論が真のボトルネック**。 |
| H3（穴埋め）でも `L2\|L0` が低い | import/signature を消しても回路を作れない＝**推論能力不足が確定**。 |
| coder は H0 ≈ H1（差小） | capable モデルはヒント不要。**ヒントの効用はモデル能力に反比例**（天井効果）。 |

## 8. 妥当性の脅威

- 環境（Qiskit 2.x）依存。別バージョンでは API ルールを更新する。
- 正例（H2）の**非リーク厳守**（答えを与えない自明回路）。
- n=10 は小さめ。主要比較（gemma の H0 vs H1）は seed を増やして固める。
- **単一ランナーに統一**しないと exp3 と同じ交絡が再発（最重要の統制）。
- ollama の生成は seed/temperature の扱いがモデル依存。再現性は seed 固定＋複数 run で担保。
