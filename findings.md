# findings — 実験知見（卒論反映用）

卒論本文・要旨に反映する実験知見をここに集約する。数値は再現可能な実験から取り、
出典（コマンド・結果ファイル）を併記する。

---

## exp1: ローカル LLM 2モデルでの baseline vs Self-Refine（2026-06-24）

### 設定

- モデル: `ollama:qwen2.5-coder:7b`（コード特化）, `ollama:gemma3:4b`（小型汎用）
- タスク: 全10種（T1_Bell〜T9_Ansatz, T3 は a/b）
- seed: 0–2（各条件 n=3）, temperature=0.7
- モード: baseline（単発生成）, Self-Refine（`--max-rounds 3`、L2 達成で停止）
- 評価: L0 コンパイル / L1 実行 / L2 出力一致（TVD or 状態ベクトル距離 < 0.05）/ L3 構造
- 再現コマンド:
  ```bash
  export OLLAMA_BASE_URL=http://localhost:11434
  python -m scripts.run_baseline --models ollama:qwen2.5-coder:7b,ollama:gemma3:4b --seeds 3 --out results/exp1.jsonl
  python -m scripts.run_baseline --models ollama:qwen2.5-coder:7b,ollama:gemma3:4b --seeds 3 --refine --max-rounds 3 --out results/exp1.jsonl
  python -m scripts.analyze results/exp1.jsonl --markdown > results/exp1_report.md
  ```
- 生データ: `results/exp1.jsonl`（120件）, 集計: `results/exp1_report.md`

### 全体結果（L2 成功率）

| モデル | baseline | refine | 差 |
|---|---|---|---|
| qwen2.5-coder:7b | 23/30 (77%) | 24/30 (80%) | +1件 |
| gemma3:4b | 0/30 (0%) | 0/30 (0%) | ±0 |
| **全体** | 23/60 (38.3%) | 24/60 (40.0%) | **+1.7%** |

失敗カテゴリ（全体）: `import` 52 / `wrong_output` 12 / `build_error` 9。
`import` はほぼ全て gemma3:4b（コンパイル前に落ちる）。

### 主要な知見（卒論の論点）

1. **支配要因はモデル能力であって Self-Refine ではない。**
   coder 7b は約8割成功、gemma 4b は 0割（L0 通過率 17%）。Self-Refine は両者の差を
   まったく埋めない。→ Self-Refine の前提として「最低限コードを書ける能力」が要る。

2. **Self-Refine が有効に働く例**: coder 7b の **T6_QFT が 67%→100%**
   （平均 1.33 ラウンド、first_success_round 平均 0.33 = 2回目で回復）。
   実行系のエラーをフィードバックして直せた典型例。

3. **【重要・負の結果】Self-Refine が退行を招く例**: coder 7b の **T8_QPE**。
   baseline では「動くが出力がズレる」(L0/L1=100%, L2 距離 0.821) だったのに、
   refine 後は **L0/L1 が 33% に低下**——出力一致を促すフィードバックで、
   動いていたコードをコンパイル不能に壊した（avg 3.00 ラウンド・回復せず）。
   → 「wrong_output を直そうとして compile/import を壊す」失敗モードが存在する。
   Self-Refine は単調改善ではない。

4. **能力不足モデルでは Self-Refine は無効**: gemma 4b は全タスクで平均 3.00 ラウンド
   ＝毎回上限まで失敗。`import` 段階を越えられず、フィードバックを与えても回復不能。

5. **coder 7b のタスク別内訳**（baseline→refine, L2）:
   T1–T4 100%→100%（容易）, T5_Grover 67%→67%, **T6_QFT 67%→100%（改善）**,
   T7_IQFT 67%→67%, **T8_QPE 0%→0%（コード健全性は退行）**, T9_Ansatz 67%→67%。
   → 改善1・退行1・他は不変。純増は1サンプルのみ。

### 限界・次の実験

- n=3/条件と小さく、+1.7% は統計的に有意とは言えない。seed を増やして固める必要。
- 強いモデル（`qwen2.5:32b`、API の gpt-5 / claude）での追試で、
  「Self-Refine が効く能力帯」を切り分けたい。
- フィードバック設計（現状は execution-feedback 型・正解非開示）の ablation も論点。

---

## exp2: 標本増（coder n=10）＋強モデル 32b（2026-06-24）

### 設定

- モデル: `ollama:qwen2.5-coder:7b`（**n=10**, seed0–9）, `ollama:qwen2.5:32b`（n=3, seed0–2）
- 他条件は exp1 と同一（全10タスク, temperature=0.7, max_rounds=3）
- 12:00 で時間切れ停止のため 32b refine は 28/30 で打ち切り（他は完走）
- 生データ: `results/exp2.jsonl`（258件）, 集計: `results/exp2_report.md`

### 結果（L2 成功率）

| モデル | baseline | refine | 差 |
|---|---|---|---|
| qwen2.5-coder:7b (n=100) | 75% | 82% | **+7pt** |
| qwen2.5:32b (n=30/28) | 77% | 89% | **+12pt** |

refine 下の階層別: coder L0 95%/L1 92%/L3 92%、32b は **L0/L1/L3 すべて100%**。

### 主要な知見（exp1 を更新・訂正）

1. **Self-Refine は両モデルで明確に有効**（標本増で確証）。coder +7pt、32b +12pt。
   平均ラウンドは coder 1.47 / 32b 1.29 で、多くは1〜2回で決着。

2. **強モデルほど Self-Refine の恩恵が大きい**。32b は refine 下で L0/L1/L3 が
   すべて100%に到達し、wrong_output だけが残課題になる。

3. **【exp1 の T8_QPE 退行は小標本ノイズだった（訂正）】**。
   n=10 では coder の**全タスクで L2 が baseline 以上**（タスク単位の退行ゼロ）。
   T8_QPE も 0%→10% と微改善。
   ただし集計 L0 は 99%→95% に微減 = 「個々のサンプルでは refine が稀に
   コンパイルを壊す」現象自体は残るが、タスク単位の正答率は下げない。
   → 卒論では「Self-Refine は集計レベルで単調改善だが、サンプルレベルでは
   稀に退行しうる（L0 の微減）」と二段構えで記述するのが正確。

4. **タスク別の伸び**（coder, base→refine, L2）: T7_IQFT 60→80, T3a 70→80,
   T6_QFT 70→80, T3b 90→100, T5_Grover 90→100。難しめのタスクで伸長し、
   容易タスク（T1/T2）は100%維持。

5. **コード特化7B ≈ 汎用32B**（baseline L2 75% vs 77%）。量子コード生成では
   モデル規模よりコード特化が効く可能性。

6. **特異点**: T4_BV は **32b が両モードで0%**（capable モデルの特定タスク盲点）。
   T8_QPE が両モデルで最難。これらはフィードバック設計だけでは救えない可能性。

### 次の実験

- 32b の n を3→10 に増やして +12pt を固める（今回は時間切れで n=3）。
- T4_BV の 32b 0% / T8_QPE 難の原因分析（プロンプト不足か、評価が厳しすぎるか）。
- API モデル（gpt-5 / claude）での上限確認と、フィードバック ablation。

---

## exp3 詳細: gemma3:4b はなぜ 0% か（失敗類型の解剖, 2026-06-30/07-01）

データ: `results/local_gemma3_4b_*.jsonl`（573サンプル: baseline 410 / refine 163）。
**全タスク・両モードで L2 = 0%**（一度も正解回路を生成できず）。失敗の内訳:

### 失敗の根本原因（支配的なのは「API の古さ」）

1. **旧 Qiskit API による import 失敗（import 424件中 405件）が最大要因**。
   - `cannot import name 'Aer' from 'qiskit'` 279件、`... 'execute' ...` 126件。
   - `Aer`/`execute` は **Qiskit 1.0 で廃止**。実行環境は Qiskit 2.x なので import 行で即死。
   - 典型例（T1_Bell）: **回路ロジックは正しい**（`h(0); cx(0,1)`、シグネチャも正しい）のに、
     `from qiskit import QuantumCircuit, transpile, Aer, execute` と
     **使ってもいない `Aer, execute` を import 行に書いた**せいで L0 失敗。
     → 推論ではなく「学習データのライブラリ版が古い」ことが原因。

2. **シグネチャ違反・API ハルシネーション（build_error 100件）**。
   - `build_circuit() missing 1 required positional argument: 'num_qubits'`（74件）
     = 規約は無引数なのに `build_circuit(num_qubits)` と定義。
   - `cnot`/`ccnot`（正: `cx`/`ccx`）、`x(q3=...)` の不正キーワード、`Qubit.state` 等の存在しない API。

3. **wrong_output（49件）**: 実行できても出力は最大級に誤り（L2距離 = 1.0）。

### Self-Refine が無効な理由
0%→0%。各ラウンドで「Aer が import できない」とフィードバックしても、**毎回また同じ旧 API を出力**し
回復しない。Self-Refine の前提（モデルが実行フィードバックを行動に反映できる）の**限界の好例**。
capable モデル（coder +7pt / 32b +12pt）との決定的な差。

### データ品質の注意（`results/local_data_quality.md`）
gemma baseline の n は不均一・重複あり: T1–T6 は 55件だが **11ラウンド×各5重複**で独立 seed ではない。
T7=16, T8=5, T9=4 はラウンド欠落。refine は T7–T9 欠落。
→ gemma の数値は「**ほぼ常に失敗**」という定性結論として扱い、精密な率としては使わない。

### 卒論への含意
gemma の 0% は**純粋な推論能力不足ではなく「対象ライブラリ版に対する知識の古さ（API ドリフト）」のアーティファクト**。
「モデル能力」軸が「学習データの新しさ」と交絡している。→ 切り分けには下記 API ヒント ablation が必要。

### 追試: API ヒントの ablation（推奨設計）
廃止 API を出させないためのヒント注入で「API 新しさ」と「推論能力」を分離する。ベストプラクティス:
1. **system プロンプトに環境契約を固定**（task は user 側）。バージョンと API 規約は毎回効かせる安定制約。
2. **バージョン明示＋記号レベルの do/don't**:
   ❌ `from qiskit import Aer, execute` / `qiskit.algorithms`、
   ✅ `from qiskit_aer import AerSimulator`・`AerSimulator().run(transpile(qc, sim))`、
   無引数 `build_circuit()`、`cx`/`ccx`（`cnot`/`ccnot` 不可）。
3. **最小の正例（few-shot 1個）** = 現行 idiom のスケルトン。小型モデルほど散文より in-context 例が効く。
4. **廃止記号を負例として明示**（各負例に正しい置換をペアで）。
5. **最小・非リーク**（与えるのはライブラリ/環境制約だけ。回路の答えは与えない）。
6. **Self-Refine の feedback も強化**: 生エラーに「Aer/execute は廃止 → qiskit_aer.AerSimulator」の修正規則を添える。
7. **能力を厳密に測る回は「穴埋めテンプレート」**（import 行＋シグネチャを与え本体だけ生成）で
   import/シグネチャ失敗クラスを構造的に排除し、回路ロジック能力だけを測る。
8. **必ずヒント有/無で ablation 計測**。
推奨既定: system 契約(1,2) ＋ few-shot 1個(3) ＋ 負例(4)。厳密計測回は穴埋め(7)併用。
