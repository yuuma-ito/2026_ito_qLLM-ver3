# 実験でLLMに渡すプロンプト一覧

実験の共通指示、全10タスクの指示、B・R・F・D・Pの条件別指示をまとめる。2026-10-13時点の実装に対応する。枠内は実装の原文を掲載し、英語の指示もそのまま示す。

## 読み方と条件の違い

モデルへの要求は、共通のsystem指示と、タスク・介入に応じたuser指示で構成する。初回と修正時の組み合わせは次のとおり。

| 条件 | 初回のuser指示 | 修正時のuser指示 |
| --- | --- | --- |
| B baseline | タスク本文 | 修正なし |
| R self_refine | タスク本文 | タスク本文＋直前コード＋自己点検の要求 |
| F execution_feedback | タスク本文 | タスク本文＋直前コード＋評価器の診断＋修正要求 |
| D self_debugging | タスク本文 | タスク本文＋直前コード＋評価器の診断＋説明・原因分析・修正の要求 |
| P preventive_spec | タスク本文＋予防的注意事項 | 修正なし |

B・R・F・Dは対応するモデル・タスク・seedで初期生成を共有する。Pは注意事項を付けて独立に初回生成する。修正条件はL3達成で終了し、未達の場合は設定された上限まで修正する。本実験では最大3回。各修正では直前のコードを使い、F・Dには直前の評価の診断も渡す。それ以前の全履歴を列挙する形式ではない。

### 目次

- [全モデル共通の指示](#全モデル共通の指示)
- [タスクごとの指示](#タスクごとの指示)
- [条件ごとの追加指示](#条件ごとの追加指示)
- [評価器が返す診断情報](#評価器が返す診断情報)
- [実装との対応と注意点](#実装との対応と注意点)

## 全モデル共通の指示

Qiskit 2.xとqiskit-aerを使い、`build_circuit()`で要求された回路を返すこと、測定は評価器に任せること、コードだけを出力することを指定する。

出典：[prompts/system.txt](../prompts/system.txt)。各LLMクライアントが共通指示として使用する。

````text
You are an expert Qiskit programmer. Generate a complete, runnable Python script using qiskit (version 2.x) and qiskit-aer.

Strict requirements:
- Import all necessary modules at the top.
- Define exactly one function named `build_circuit() -> QuantumCircuit`.
- The function must return a QuantumCircuit with the requested number of qubits.
- DO NOT add measurement operations inside `build_circuit`. Measurement is added by the evaluator.
- Output ONLY the Python code in a single fenced block: ```python ... ```
- No explanation outside the code block.
````

## タスクごとの指示

以下から対象タスクの本文1つをuser指示に使用する。評価器の期待値・正解コード全体を追加して渡す形式ではない。

### T1_Bell Bell state (2-qubit)

量子ビット数：2。難度：easy。出典：[tasks/t1_bell.py](../tasks/t1_bell.py)。

````text
Task: Construct the Bell state (|00⟩ + |11⟩) / √2 on 2 qubits.

Expected behavior:
- Apply H to qubit 0, then CNOT with qubit 0 as control and qubit 1 as target.
- After execution, measuring all qubits should yield "00" with probability 0.5 and "11" with probability 0.5.

Number of qubits: 2
````

### T2_GHZ GHZ state (3-qubit)

量子ビット数：3。難度：easy。出典：[tasks/t2_ghz.py](../tasks/t2_ghz.py)。

````text
Task: Construct the GHZ state (|000⟩ + |111⟩) / √2 on 3 qubits.

Expected behavior:
- Apply H to qubit 0, then CNOT(0, 1), then CNOT(1, 2).
- After execution, measuring all qubits should yield "000" with probability 0.5 and "111" with probability 0.5.

Number of qubits: 3
````

### T3a_DJ_constant Deutsch-Jozsa (constant, n=2)

量子ビット数：3。難度：medium。出典：[tasks/t3_dj_constant.py](../tasks/t3_dj_constant.py)。

````text
Task: Implement the Deutsch-Jozsa algorithm for the constant function f(x1, x2) = 0 (the all-zero function).

Setup:
- 3 total qubits: q0 and q1 are input qubits, q2 is the ancilla.
- The ancilla q2 must be initialized to |1⟩ (apply X gate before the H gates).
- After Hadamards, apply the oracle for f (identity for constant 0; do nothing).
- Apply Hadamards on the input qubits q0 and q1 only (NOT the ancilla).

Expected: input qubits q0, q1 deterministically measure as "00" (constant detected).
The ancilla measurement is 50/50 between 0 and 1.

Number of qubits: 3
````

### T3b_DJ_balanced Deutsch-Jozsa (balanced x1 XOR x2)

量子ビット数：3。難度：medium。出典：[tasks/t3_dj_balanced.py](../tasks/t3_dj_balanced.py)。

````text
Task: Implement the Deutsch-Jozsa algorithm for the balanced function f(x1, x2) = x1 XOR x2.

Setup:
- 3 total qubits: q0 and q1 are input qubits, q2 is the ancilla.
- Initialize ancilla q2 to |1⟩ (X gate first).
- Apply H to all 3 qubits.
- Oracle for f = x1 XOR x2: CNOT(q0, q2), CNOT(q1, q2).
- Apply final H on input qubits q0 and q1 only.

Expected: input qubits q0, q1 deterministically measure as "11" (balanced detected).
The ancilla measurement is 50/50.

Number of qubits: 3
````

### T4_BV_011 Bernstein-Vazirani (s=011, n=3)

量子ビット数：4。難度：medium。出典：[tasks/t4_bv.py](../tasks/t4_bv.py)。

````text
Task: Implement the Bernstein-Vazirani algorithm to recover the hidden bitstring s = "011" (binary).

Bitstring convention: s is read as bits (s[2], s[1], s[0]) where s[i] corresponds to qubit i.
So s[0]=1, s[1]=1, s[2]=0.

Setup:
- 4 total qubits: q0, q1, q2 are the query register, q3 is the ancilla.
- Initialize ancilla q3 to |1⟩ (X gate).
- Apply H to all 4 qubits.
- Oracle for f(x) = s · x = (s[0]·x[0] + s[1]·x[1] + s[2]·x[2]) mod 2:
  - Apply CNOT(q_i, q3) for each i where s[i] = 1.
  - For s = "011": apply CNOT(q0, q3) and CNOT(q1, q3).
- Apply final H on the query qubits q0, q1, q2.

Expected: q0, q1, q2 measure as "011" (= s) with certainty. Ancilla q3 measures 50/50.

Number of qubits: 4
````

### T5_Grover_11 Grover search (n=2, marked=11)

量子ビット数：2。難度：medium。出典：[tasks/t5_grover.py](../tasks/t5_grover.py)。

````text
Task: Implement Grover's search algorithm on 2 qubits with the marked state |11⟩, using exactly one Grover iteration.

For n=2 and 1 marked state, the Grover iteration produces the marked state with probability 1 (exact).

Algorithm:
1. Initialize 2 qubits in uniform superposition (H on both).
2. Apply oracle that marks |11⟩ with a phase flip: e.g., CZ(0,1).
3. Apply diffusion operator (inversion about the mean): H on all, X on all, CZ(0,1), X on all, H on all.

Expected: measuring should yield "11" with probability 1.

Number of qubits: 2
````

### T6_QFT_001 QFT (n=3, input |001⟩)

量子ビット数：3。難度：hard。出典：[tasks/t6_qft.py](../tasks/t6_qft.py)。

````text
Task: Apply the 3-qubit Quantum Fourier Transform (QFT) to the input state |001⟩.

In Qiskit's little-endian convention, |001⟩ means qubit 0 = |1⟩ and qubits 1, 2 = |0⟩.

Algorithm:
1. Initialize the input state by applying X to qubit 0.
2. Apply QFT to all 3 qubits. You may use qiskit.circuit.library.QFT or implement it manually.
   Use the standard convention with swap gates at the end (do_swaps=True).

The expected output statevector is determined by the canonical QFT mapping:
QFT|j⟩ = (1/√N) Σ_k exp(2πi · j · k / N) |k⟩  with N = 2^3 = 8

Number of qubits: 3
````

### T7_IQFT_001 Inverse QFT (n=3, input |001⟩)

量子ビット数：3。難度：hard。出典：[tasks/t7_iqft.py](../tasks/t7_iqft.py)。

````text
Task: Apply the INVERSE 3-qubit Quantum Fourier Transform (inverse QFT, IQFT) to the input state |001⟩.

In Qiskit's little-endian convention, |001⟩ means qubit 0 = |1⟩ and qubits 1, 2 = |0⟩.

Algorithm:
1. Initialize the input state by applying X to qubit 0.
2. Apply the INVERSE QFT (not the forward QFT) to all 3 qubits.
   You may use qiskit.circuit.library.QFT with inverse=True, or implement it manually.
   Use the standard convention with swap gates (do_swaps=True).

Note: the inverse QFT is the conjugate transpose of the forward QFT; getting the direction
(sign of the phase rotations) and the swap placement right is essential.

Number of qubits: 3
````

### T8_QPE_001 Quantum Phase Estimation (phi=1/4, 3 counting qubits)

量子ビット数：4。難度：hard。出典：[tasks/t8_qpe.py](../tasks/t8_qpe.py)。

````text
Task: Implement 3-bit Quantum Phase Estimation (QPE) for the single-qubit phase gate P(theta)
with theta = pi/2, acting on its eigenstate |1>.

Setup (4 qubits total):
- Qubits 0, 1, 2: the counting register (3 estimation qubits).
- Qubit 3: the eigenstate register, prepared in |1> (eigenstate of P(theta) with eigenvalue e^{i*theta}).

Algorithm:
1. Apply X to qubit 3 to prepare the eigenstate |1>.
2. Apply H to each of the counting qubits 0, 1, 2.
3. For each counting qubit j (j = 0, 1, 2), apply controlled-P(theta) with qubit j as control and
   qubit 3 as target, repeated 2**j times (equivalently controlled-P(theta * 2**j)).
4. Apply the inverse QFT to the counting register (qubits 0, 1, 2).

Since theta = pi/2 corresponds to phase phi = theta/(2*pi) = 1/4 = 0.010 in binary, the counting
register should deterministically encode the estimate. Do NOT add measurements; the evaluator adds them.

Number of qubits: 4
````

### T9_Ansatz_001 Parameterized hardware-efficient ansatz (2-qubit, fixed angles)

量子ビット数：2。難度：hard。出典：[tasks/t9_ansatz.py](../tasks/t9_ansatz.py)。

````text
Task: Build a 2-qubit hardware-efficient ansatz with the following exact structure and fixed
rotation angles (in radians). Apply the operations in this order:

1. RY(pi/4) on qubit 0
2. RY(pi/3) on qubit 1
3. CX with qubit 0 as control and qubit 1 as target
4. RY(pi/6) on qubit 0
5. RY(pi/5) on qubit 1

This is a single-entangling-layer ansatz: a layer of parameterized RY rotations, one CX entangler,
then a second layer of RY rotations. Use the angle values exactly as given. Do NOT add measurements.

Number of qubits: 2
````

## 条件ごとの追加指示

`{タスク本文}`、`{直前コード}`、`{評価器の診断情報}`は実行時に置き換わる部分である。F・Dの診断情報は直前の評価結果から作られる。

### B 初回生成のみ

user指示は選んだタスク本文のみ。条件専用の注意事項や修正指示は追加しない。

### R 外部評価を渡さず自己点検

直前コードを自分で点検し、問題があれば修正するよう求める。

````text
{タスク本文}

--- 前回のコード ---
あなたは前回、以下のコードを生成しました。外部のテスト結果や正解は与えません。

```python
{直前コード}
```

このコードを自分で慎重に点検してください。タスク要件、Qiskit API、量子回路の意味、build_circuit() の仕様を確認し、問題がある場合は修正してください。
最終的に、完全な修正版 Python コードだけを ```python ``` ブロックで出力してください。
````

### F 実行結果を渡して修正

直前コードと評価器の診断を渡して修正を求める。

````text
{タスク本文}

--- 前回の試行結果 ---
あなたは以下のコードを生成しましたが、実行ベース検証に失敗しました。

```python
{直前コード}
```

検証器から得られた情報:
{評価器の診断情報}

この実行フィードバックを使って問題を修正し、完全な Python コードを ```python ``` ブロックで出力してください。
````

### D 説明と原因分析を伴う修正

直前コードと評価器の診断を渡し、説明・原因分析・修正を求める。説明と分析はコード内のコメント3〜6行に残す。

````text
{タスク本文}

--- 前回の試行結果 ---
```python
{直前コード}
```

検証器から得られた情報:
{評価器の診断情報}

次の順序で自己デバッグしてください。
1. 前回コードが何をしているかを説明する。
2. タスク要件と検証結果を照合し、失敗原因を特定する。
3. 原因を踏まえてコードを修正する。
4. system の『コードブロックのみ』制約を守るため、説明と原因分析は 修正版コードブロック先頭の Python コメント（# DEBUG: ...）として 3〜6 行残す。その後に完全な修正版コードを書く。
````

### P 生成前の予防的注意事項

タスク本文の後ろに空行を挟み、次の注意事項を追加して1回生成する。

````text
量子コード生成では以下の点に注意してください。

1. 指定された関数名と戻り値形式を必ず守ること。
2. Qiskitに存在しないAPIを使用しないこと。
3. 量子ビット数と古典ビット数を一致させること。
4. 測定結果のビット順序に注意すること。
5. 期待される測定分布または状態ベクトルと一致する回路を作ること。
6. 不要なゲートを追加しないこと。
7. 指定されたインターフェースを必ず実装すること。
````

## 評価器が返す診断情報

F・Dでは[harness/refine.py の diagnose](../harness/refine.py)が直前の評価から診断文を構築する。出力される情報は評価段階に応じて変わる。

| 状況 | 診断に含まれる情報 |
| --- | --- |
| コード実行失敗 | エラー分類と例外メッセージ |
| 回路構築時の失敗 | build_circuit呼び出しの例外メッセージ |
| 量子ビット数の不一致 | 不一致の説明と量子ビット数の修正要求 |
| シミュレーション失敗 | エラー分類と例外メッセージ |
| 分布の不一致 | 距離・閾値、期待分布と取得できた実測分布（それぞれ上位8項目） |
| 状態ベクトルの不一致 | 距離・閾値とゲートの見直し要求。振幅列全体は渡さない |

期待分布を提示するため、F・Dは外部の期待値情報も利用する条件である。正解の回路コードを渡す形式ではない。

## 実装との対応と注意点

- 共通system指示：[prompts/system.txt](../prompts/system.txt)、読み込み：[harness/llm_clients.py](../harness/llm_clients.py)。
- タスク本文：[tasks/](../tasks/)。
- 初回・修正のuser指示：[harness/interventions/prompts.py](../harness/interventions/prompts.py)。Pの実行時本文は同ファイルの`PREVENTIVE_SPEC`定数であり、[prompts/preventive_spec.txt](../prompts/preventive_spec.txt)は対応する別ファイル。
- 診断文：[harness/refine.py](../harness/refine.py)の`diagnose`。同ファイルの旧`build_feedback_prompt`ではなく、現行の条件比較では`build_intervention_prompt`を使う。
- 呼び出し・終了条件：[harness/runner.py](../harness/runner.py)。

Pの原文には「量子ビット数と古典ビット数を一致させること」がある一方、共通指示は測定を評価器に任せる。この注意事項の解釈は回路の古典ビット構成に影響し得るため、今後のプロンプト見直しで確認する対象になる。

掲載内容は現在の実装である。検証済み集計にはschema 2.0と2.1の診断文処理差が含まれ、過去の全要求がこの本文と完全に一致したと断定しない。実験の保存設定と実施時点も併せて参照する。
