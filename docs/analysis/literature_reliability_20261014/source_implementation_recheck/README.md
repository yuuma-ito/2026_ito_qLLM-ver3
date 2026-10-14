# 原文と実装の対応の再点検

対象は[前報告](../README.md)。本番の評価器はevaluation_policy_v4のまま保持し、5,000件の再評価は開始していない。今回の重点は、原文の取得証拠と実際の実装・検証範囲を結び付けることである。

## 前報告から明確にした点

1. 前報告の公開成果物には原文PDFの取得日時・hash・節ごとのPDFページ番号が不足していた。今回はPDFを再取得し、HTTP応答・日時・bytes・SHA-256・抽出テキストhash・確認ページのhashを保存した。**今回の証拠は今回の再取得を示し、前回の取得日時を遡って証明するものではない。**
2. 密度行列の補助検査、複数入力、パラメータ族、メタモルフィック関係、mutation、Wilson区間の多くは**監査用コード**である。本番evaluateへ全機能を実装したと読まないよう区別した。
3. fidelity 0.9975、距離0.05、shots・seed・ゲート数範囲などを、論文が指定した基準とは扱わない。特に0.9975と距離0.05の厳密な対応は一致しない。
4. 現RはMadaanらのSelf-Refineの忠実な再現ではない。手順の相違を確認したうえで、自己点検修正の派生条件とした。
5. QFTの監査入力には未検査の列位相が残る反例を追加した。「複数入力を検査した」と「変換全体の同値性を確認した」を区別する。

## 4段階の読み方

| 段階 | この報告での意味 |
| --- | --- |
| 原文確認済み | 指定した原文の該当箇所を確認した。実装済みという意味ではない |
| 実装確認済み | ファイル・関数・動作確認を対応付けた。監査用か本番用かを別欄に示す |
| 独立検証済み | 期待値を本番評価器の同じ関数から作らず、別の数式・手計算・既知状態で選んだケースを照合した |
| 未確認 | 原文未取得、または対象とする本番機能・条件が未実装／未検証 |

段階は**項目と適用範囲ごと**に付ける。原文の確認、実装、独立検証は別の属性なので、1資料全体へ最上位ラベルを付けて保証しない。独立なのは期待値の構築方法であり、Qiskitの回路構築・実行スタックから完全に独立したことや、全ケースへの健全性・完全性を証明したことではない。

## 原文取得の証拠と具体的な記述

全hashと取得日時は[source_receipts.json](source_receipts.json)に保存した。PDF本文・抽出テキストはローカルの`.cache/literature_sources/provenance_20261014/`に保存し、Gitへ追加しない。以下のページは**PDFビューアの1始まりのページ番号**。誌面ページと混同しない。資料の内容は日本語で要約し、原文の未確認箇所を補わない。

| 資料 | 取得証拠 | 節とPDFページ | 原文の具体的な記述の要約 | 判定 |
| --- | --- | --- | --- | --- |
| R1 Paltenghi & Pradel, arXiv v1 | HTTP 200、36頁、SHA-256 `6394250bea…` | [§4.1 p.8](https://arxiv.org/pdf/2410.00650v1#page=8)、[§4.3.2 p.12](https://arxiv.org/pdf/2410.00650v1#page=12)、§4.3.3 p.13、§7.2 p.27 | 入力空間の大きさ、距離と統計検定による出力オラクル、同値性オラクル、gate挿入・削除・置換などのmutationを整理する | 原文確認済み |
| R2 quantum_info・Statevector | 指定ミラーHTML 2件がHTTP 200。全hashはreceipt、ローカルAPIは別hash | [state_fidelity / process_fidelity](https://qiskit.qotlabs.org/docs/api/qiskit/quantum_info)、[equiv / reset](https://qiskit.qotlabs.org/docs/api/qiskit/qiskit.quantum_info.Statevector) | 忠実度、全体位相を除く同値性、部分resetが測定分岐を選ぶ挙動を説明する | 原文確認済み（指定仕様ミラー） |
| R3 Barr et al., UCL PDF | HTTP 200、19頁、SHA-256 `0572def3bf…` | [§2.3 p.4](https://discovery.ucl.ac.uk/id/eprint/1471263/1/06963470.pdf#page=4)、§4.3.1 p.8、[§5.1・§5.2 p.9](https://discovery.ucl.ac.uk/id/eprint/1471263/1/06963470.pdf#page=9) | 健全性・完全性、抽象仕様の不足、pseudo oracle、複数実行の関係を使う部分オラクルを説明する | 原文確認済み |
| R4 Abreu et al. | [ACM PDF](https://dl.acm.org/doi/pdf/10.1145/3528230.3529189)への取得がHTTP 403 | 該当節・ページは不明 | 本文未確認。方法・関係式・結果を推測しない | 未確認 |
| R5 Chen et al., PDF内の版はarXiv v2 | HTTP 200、35頁、SHA-256 `ebae72ea0e…` | [§2.1 p.2](https://arxiv.org/pdf/2107.03374#page=2)、[Eq.1・Figure 3 p.3](https://arxiv.org/pdf/2107.03374#page=3)、[§2.3 p.4](https://arxiv.org/pdf/2107.03374#page=4) | 実行テストによる機能的評価、n候補とc成功によるpass@k、gVisorとnetwork制限を用いたsandboxを記載する | 原文確認済み |
| R6 Madaan et al., arXiv v2 | HTTP 200、54頁、SHA-256 `81e4459231…` | §2 pp.2–4、[Algorithm 1 p.3](https://arxiv.org/pdf/2303.17651v2#page=3)、[Eq.4と最終出力 p.4](https://arxiv.org/pdf/2303.17651v2#page=4) | 同じモデルで生成・feedback・refineを行い、履歴を付加し、停止後の最後の出力を返す | 原文確認済み |

R2のユーザー指定URLはサイト上でIBM Quantum Documentation Mirrorと表記される。今回のHTML hashはそのミラーの取得証拠であり、IBMの配信元や特定版のHTMLと同一であることまで確認した証拠ではない。ローカルのQiskit 2.5.2・Aer 0.17.2は[installed_api_recheck.json](installed_api_recheck.json)のsignature・ソースhashと実行テストで別途照合した。latestページを2.5.2の固定仕様だと仮定しない。

R4は実装根拠から除外する。他資料がR4を紹介していることも、原文取得の代わりにはしない。

## 論文の記述から実装への対応

- **R1**は監査の分類と入力・終端出力・距離・同値性・mutationの動機として用いた。MorphQ、ZX/SAT等の個別手法を実装したわけではない。特定のTVD閾値や検査入力は本プロジェクトが選んだ。
- **R2**は忠実度、全体位相、resetの仕様の確認に用いた。ユニタリ回路へ限定するv4方針は、その仕様を踏まえた独自の保守的設計であり、Qiskitがすべての非ユニタリ回路を拒否すべきと要求したわけではない。
- **R3**は仕様と観測の対応、部分オラクル、関係による検査の位置付けに用いた。今回の3変換やL0〜L3分類を論文からそのまま移植したわけではない。
- **R5**の機能的評価・隔離の考え方は参照したが、pass@kもgVisor sandboxも本番へ実装していない。単なるsubprocess timeoutを論文のsandboxと同じものにしない。
- **R6**と現Rには明確な相違がある。現Rはfeedbackとrefineを1要求にまとめ、全履歴を渡さず、外部L3で停止する。原論文と同じ手順や効果を検証したとは判断しない。

## 実装とテストの対応表

段階の集計は原文確認済み2項目、実装確認済み8項目、独立検証済み9項目、未確認2項目、計21項目。これは論文の件数ではない。[traceability.json](traceability.json)に、関数・テストの行番号とhash、理論・条件・限界を保存した。全関数名を現在のASTで存在確認した。

| 項目 | 段階と実装範囲 | 実装箇所 | 検証の対応 |

| --- | --- | --- | --- |
| 全体位相を除く状態距離 | 独立検証済み / production | `harness/evaluator.py:_statevector_distance` | `tests/test_evaluation_audit.py:test_production_phase_alignment_matches_independent_formula` |
| TVDの計算 | 独立検証済み / production | `harness/evaluator.py:_tvd` | `tests/test_source_implementation_recheck.py:test_tvd_agrees_with_hand_computed_distributions` |
| 量子ビット順への測定結果復元 | 独立検証済み / production | `harness/readout.py:prepare_readout`<br>`harness/readout.py:project_counts` | `tests/test_canonical_readout.py:test_explicit_readout_mapping_and_structural_constraints` |
| 非ユニタリ回路の主状態ベクトル評価拒否 | 独立検証済み / production | `harness/evaluator.py:_run_statevector` | `tests/test_literature_reliability.py:test_primary_does_not_compare_a_sampled_nonunitary_branch`<br>`tests/test_literature_reliability.py:test_reset_ensemble_matches_independent_density_matrix` |
| 密度行列の補助オラクル | 独立検証済み / audit_only | `scripts/audit_literature_reliability.py:quantum_checks` | `tests/test_literature_reliability.py:test_reset_ensemble_matches_independent_density_matrix` |
| 状態忠実度による補助mutation検出 | 独立検証済み / audit_only | `scripts/audit_literature_reliability.py:overlap_fidelity`<br>`scripts/audit_literature_reliability.py:mutation_checks` | `tests/test_literature_reliability.py:test_unitary_preparation_and_global_phase_are_supported` |
| QFT/IQFTの複数入力 | 独立検証済み / audit_only | `scripts/audit_literature_reliability.py:quantum_checks` | `tests/test_literature_reliability.py:test_per_column_phase_passes_basis_but_fails_coherent_input`<br>`tests/test_source_implementation_recheck.py:test_current_qft_input_set_does_not_cover_other_column_phases` |
| パラメータ族 | 独立検証済み / audit_only | `scripts/audit_literature_reliability.py:quantum_checks` | 監査CSVの確認例 |
| メタモルフィック変換 | 独立検証済み / audit_only | `scripts/audit_literature_reliability.py:quantum_checks` | `tests/test_evaluation_audit.py:test_barriers_do_not_violate_gate_count_bounds`<br>`tests/test_evaluation_audit.py:test_production_phase_alignment_matches_independent_formula` |
| プロセスのtimeout例 | 実装確認済み / audit_only | `scripts/audit_literature_reliability.py:controlled_process_checks` | 監査CSVの確認例 |
| 本番sandbox・再評価executor | 未確認 / not_implemented | 本番実装なし | 対応する本番テストなし |
| pass@k | 原文確認済み / not_implemented | 本番実装なし | 対応する本番テストなし |
| Self Refine原論文との対応 | 実装確認済み / production_variant | `harness/interventions/prompts.py:build_intervention_prompt`<br>`harness/runner.py:run_intervention` | `tests/test_interventions_v2.py:test_self_refine_does_not_include_execution_diagnosis` |
| 段階・失敗分類 | 実装確認済み / production | `harness/evaluator.py:evaluate`<br>`harness/evaluator.py:_exec_code`<br>`harness/evaluator.py:_try_build` | `tests/test_failure_metadata.py:test_stage_and_cause`<br>`tests/test_canonical_readout.py:test_partial_readout_is_model_interface_failure` |
| 最初・途中・最後の成功 | 実装確認済み / production_and_audit | `harness/runner.py:_record`<br>`scripts/audit_literature_reliability.py:summarize_history` | `tests/test_literature_reliability.py:test_history_distinguishes_first_ever_final_and_regression` |
| 破損・重複の再開拒否 | 実装確認済み / production | `harness/experiment.py:load_existing` | `tests/test_literature_reliability.py:test_resume_rejects_corrupt_file_without_rewriting`<br>`tests/test_literature_reliability.py:test_valid_resume_preserves_existing_records` |
| 評価器版・sampling方針の統合防止 | 実装確認済み / production | `scripts/pool_experiments.py:signature`<br>`scripts/run_experiment.py:_check_evaluator_resume` | `tests/test_literature_reliability.py:test_pool_signature_separates_evaluator_versions_and_sampling`<br>`tests/test_canonical_readout.py:test_resume_does_not_mix_evaluator_versions` |
| Wilson区間 | 実装確認済み / audit_only | `scripts/audit_literature_reliability.py:wilson_interval` | `tests/test_literature_reliability.py:test_wilson_interval_handles_extremes_and_invalid_denominators` |
| shots・seed・閾値の感度 | 実装確認済み / production_parameters_and_audit_model | `harness/evaluator.py:_run_distribution`<br>`scripts/audit_literature_reliability.py:sampling_sensitivity` | `tests/test_evaluation_audit.py:test_distribution_simulation_is_reproducible` |
| process fidelity・形式的同値性 | 原文確認済み / not_implemented | 本番実装なし | 対応する本番テストなし |
| Abreuらの手法 | 未確認 / not_implemented | 本番実装なし | 対応する本番テストなし |

## 各方法の理論的根拠と適用条件

### M01 全体位相を除く状態距離

**根拠**：R2: Statevector.equiv / state_fidelity。正規化純粋状態ではd²=2−2|a†b|=2−2√F。距離式はAPI忠実度からの独自の代数的導出であり、論文の実験閾値ではない。

**適用条件**：同じ次元・正規化・純粋状態。

**限界・未適用範囲**：検算した位相と12組の状態に限定。混合状態・任意チャネルは対象外。

### M02 TVDの計算

**根拠**：R1: §4.3.2, PDF p.12（距離の分類）。TVD=½Σ|p−q|を本実装の数学的定義として検算。R1の当該箇所は尺度を列挙し、この実装を指定しない。

**適用条件**：同じ出力空間の正規化分布。

**限界・未適用範囲**：3組の手計算との一致。相対位相・状態の等価性は検査しない。

### M03 量子ビット順への測定結果復元

**根拠**：R2: bit ordering / measure_all, installed API。各測定先c(q)からq[n−1]…q[0]へ投影し、未使用古典ビットを周辺化する。本番での正規化方針は独自設計。

**適用条件**：全量子ビットの一意な終端測定。

**限界・未適用範囲**：手作り基底例で独立確認。指定古典ビットへの配置要求は別の構造検査が必要。

### M04 非ユニタリ回路の主状態ベクトル評価拒否

**根拠**：R2: Statevector.reset / DensityMatrix / Operator。ユニタリUの列0は全ゼロ入力の純粋出力。部分resetは混合状態の分岐を返し得るため、拒否する保守的な独自方針。

**適用条件**：ユニタリ回路、固定全ゼロ入力、現在の小規模回路。

**限界・未適用範囲**：正しいinitialize等も除外する。Qiskitが非ユニタリを評価できないとの主張ではない。

### M05 密度行列の補助オラクル

**根拠**：R2: DensityMatrix.from_instruction / state_fidelity。Bellの部分resetのensembleを独立なdiag(½,0,½,0)と比較。

**適用条件**：手作りreset例。

**限界・未適用範囲**：本番evaluateへ補助densityの記録を追加していない。単一基底のcountsだけからdensityを復元しない。

### M06 状態忠実度による補助mutation検出

**根拠**：R2: state_fidelity；R1: §7.2, PDF p.27（mutationの背景）。正規化純粋状態F=|a†b|²。Bell/GHZ期待値は解析的なベクトル。

**適用条件**：6種類の非等価な意味的変異。

**限界・未適用範囲**：6/6はこの集合だけ。本番の全件補助評価・アルゴリズム完全性は未実装。0.9975は独自の試行値。

### M07 QFT/IQFTの複数入力

**根拠**：R1: §4.1, PDF p.8（入力空間の背景）。DFTをNumPyの式から独立に構築。基底ごとの位相は重ね合わせ入力で識別できる。

**適用条件**：既知mockの最初のXを確認して除去した変換。8基底＋2重ね合わせ。

**限界・未適用範囲**：一般の生成コードから入力準備を自動で除去できない。本番は固定入力のまま。 2重ね合わせは基底0と1だけを含むため、列2の位相反転を見逃す追加反例を確認。

### M08 パラメータ族

**根拠**：R1: §4.1, PDF p.8（動機のみ）。RY(θ)|0⟩=[cos(θ/2),sin(θ/2)]を独立な期待値として4角度で確認。

**適用条件**：手作り1量子ビットRYの4角度。

**限界・未適用範囲**：全Ansatz・QPEのパラメータ族ではない。原文がこの4角度を指定したわけではない。

### M09 メタモルフィック変換

**根拠**：R1: §4.1, PDF p.8；R3: §5.2, PDF p.9。全体位相・XX=I・barrierは意味的出力を保存する独自の関係。

**適用条件**：既存mock10個に3変換、L2の維持を確認。

**限界・未適用範囲**：R4の手法ではない。R1のMorphQやR3の全手法を再現したものでもない。全L3や全変換は保証しない。

### M10 プロセスのtimeout例

**根拠**：R5: §2.3, PDF p.4（隔離の動機）。subprocessのtimeoutと終了値を信頼済みsnippetで確認。

**適用条件**：合成4例のみ。

**限界・未適用範囲**：セキュリティsandbox・孫プロセス停止・CPU/memory制限を実装したことにはならない。

### M11 本番sandbox・再評価executor

**根拠**：R5: §2.3, PDF p.4。ホスト・network保護の必要性を参考にする。

**適用条件**：実際の生成コードに到達制限・資源制限・時間制限を適用することが条件。

**限界・未適用範囲**：コードの本番境界と再評価のcheckpointは未検証。NO-GO。

### M12 pass@k

**根拠**：R5: §2.1 / Eq.1 / Figure 3, PDF pp.2–3。n候補中c成功からk候補の成功指標を計算する原文の設定。

**適用条件**：原文と同じ候補生成・選択条件を満たす必要。

**限界・未適用範囲**：適応的な修正roundを独立候補と同一視できない。本実験でpass@kは実装・算出していない。

### M13 Self Refine原論文との対応

**根拠**：R6: §2, PDF pp.2–4 / Algorithm 1 p.3 / Eq.4 p.4。原文はfeedbackとrefineの別要求・履歴・停止・最終出力。

**適用条件**：現Rは同一モデルの自己点検修正という派生条件。

**限界・未適用範囲**：現Rは1要求に統合、全履歴なし、外部L3停止。原論文の忠実な再現と独立な効果検証は未確認。

### M14 段階・失敗分類

**根拠**：R3: §2.3, PDF p.4（仕様の背景のみ）。L0〜L3・taxonomyは本プロジェクトの独自契約。

**適用条件**：現在のエラーと段階定義。

**限界・未適用範囲**：論文がこのtaxonomyを指定していない。未分類例や実行基盤エラー全般を完全に識別する保証ではない。

### M15 最初・途中・最後の成功

**根拠**：R6: §2, PDF p.4（last出力） / その他は独自設計。本番のfirst_success_roundとfinal_successを、監査のever・退行案と区別。

**適用条件**：保存された連続roundの履歴。

**限界・未適用範囲**：監査案の全列を再評価用本番集計へ追加してはいない。存在しない後続roundは不明。

### M16 破損・重複の再開拒否

**根拠**：指定6資料に直接の方式指定なし：独自運用設計。同じrecord keyと不正なJSONを拒否し、入力を保持する。

**適用条件**：通常実験JSONLの読込。

**限界・未適用範囲**：原子的checkpoint、二重worker排他、本番再評価のexactly-onceを保証しない。

### M17 評価器版・sampling方針の統合防止

**根拠**：指定6資料に直接の方式指定なし：独自運用設計。比較signatureに版・sampling・状態方針を含める。

**適用条件**：現在の比較・新規生成workflow。

**限界・未適用範囲**：コードhashやtask仕様の全差分を同じsignatureで自動検証することまでは確認していない。

### M18 Wilson区間

**根拠**：指定6資料をWilson式の出典として使わない：独自採用。二項模型の比率区間を計算する監査用関数。

**適用条件**：独立な二項反復。95%水準は独自設定。

**限界・未適用範囲**：端点の検査だけでcoverageを検証したとは扱わない。5,000条件記録の本番CI・cluster設計は未実装。

### M19 shots・seed・閾値の感度

**根拠**：R1: §4.3.2, PDF p.12（閾値・標本の背景）。seed固定で再現性を確認し、二項模型の108組を計算。数値は独自設定。

**適用条件**：固定環境の再現と二値分布の模型。

**限界・未適用範囲**：全タスクの誤判定率ではない。seed固定でも境界の不確かさは消えない。

### M20 process fidelity・形式的同値性

**根拠**：R2: process_fidelity；R1: §4.3.3, PDF p.13。チャネルや変換の比較という別の評価対象を参照。

**適用条件**：変換・チャネル・入力interfaceを定義できる場合。

**限界・未適用範囲**：本番の全変換同値性、ZX/SATなどの形式検証は実装していない。Operatorの使用だけで再現したとはしない。

### M21 Abreuらの手法

**根拠**：R4: 本文未取得、根拠から除外。本文未確認。

**適用条件**：本文の取得・該当箇所確認が先。

**限界・未適用範囲**：他論文の引用・書誌情報から方法や結果を補わない。

## 文献に裏付けられていない数値・判定規則

| 設定 | 出典として扱うもの | 確認した範囲 |
| --- | --- | --- |
| TVD・状態距離の閾値0.05 | 本プロジェクトの独自設定 | R1のp値0.05の議論はTVD 0.05の根拠にはならない |
| 補助fidelity 0.9975 | mutation試行用の独自値 | 主判定の厳密な換算ではない。6変異の検出結果だけ |
| shots 8,192、seed 42 | 再現性と費用の独自設定 | 固定環境での再現を確認。一般的な誤判定率は未検証 |
| seed 10/42/99、shots 1,024/8,192/65,536、閾値0.01/0.05/0.1 | 108組の感度分析の独自条件 | 二項模型の例であり、全量子タスクの保証ではない |
| gate数の上下限、L0〜L3、interface_mismatch分類 | task・ハーネスの独自契約 | 文献のアルゴリズム正当性検査と同一ではない |
| Operator.is_unitaryの既定許容誤差 | インストール済みSDKの規約 | 数値近似による判定。数学的な厳密ユニタリ性の証明ではない |
| Wilsonの95%水準、監査の0.25秒timeout | 監査用の独自選択 | 本番CI・実行予算の妥当性は別途必要 |

正規化純粋状態の距離をd、fidelityをFとすると、`d²=2−2√F`。`d<0.05`に厳密に対応するのは **F>0.9975015625** である。監査用mutationは **F<0.9975で検出** するため、境界・等号も含めて同じ基準ではない。両閾値の間の状態を作ると主状態距離は不合格、試行fidelity条件では非検出になることを追加テストで確認した。この再点検では主判定・試行値を変更せず、その相違を記録する。

## 追加で確認した適用不能・見逃しの例

QFTの監査は8基底と、基底0・1だけを使う2つの重ね合わせに対する確認だった。DFTの列2だけに−1を掛けた別のユニタリ変換は、この10入力のfidelityをすべて1に保つ。しかし基底0と2の重ね合わせではfidelityが0になる。したがって、今回の入力集合の成功を変換全体の同値性へ拡張してはいけない。生成コードは入力準備込みのbuild_circuitしか返さないため、任意入力の変換を自動で取り出すには別のinterfaceと仕様が必要である。

ほかにも次を区別する。

- Bell/GHZの同じ分布・異なる相対位相：分布主仕様では通る。要求された状態の同値性は別の補助検査が必要。
- reset/initialize：密度行列で評価できる場合も、v4の主状態ベクトル仕様では拒否する。除外を量子計算そのものの不正解と一括しない。
- RYの4角度：Ansatz・QPEの全パラメータや一般入力へ適用済みとはしない。
- quantum_infoのprocess fidelity：チャネルと変換を定義できない固定出力APIへ、そのまま付けることはできない。
- pass@k：feedbackに依存した適応的な修正履歴を、原論文の候補集合と同じ設定として扱わない。
- Self-Refine：現在のRとの手順差・追加生成予算・外部停止を含めずに、原論文の効果を再現したと主張しない。
- メタモルフィック関係：非ユニタリや古典制御を含む場合に、選んだ変換の意味保存が自動で成立すると仮定しない。
- Wilson区間：task・seed・出典や共有初期の相関を無視した5,000件の独立二項試行へ適用しない。

## 検証結果と今回変更した範囲

対象テスト80件成功、Qiskit非推奨警告20件。追加した3テストは手計算TVD、閾値の非同値、QFT列2位相の見逃しである。詳細は[verification_results.json](verification_results.json)。以前の全276テスト成功は前回監査の記録として保持し、今回すべてを再実行したと書き換えない。

本番評価器と主判定は変更していない。対象README・参考文献の確認箇所・対応表を更新し、取得証拠と追加テストを保存した。過去のCSV・5,000件のコード・判定は保持した。テストや原文確認の成功だけで、主オラクルの一般的妥当性を証明したとは判断しない。

**本番再評価は引き続きNO-GO**。本番のsandbox、資源・時間制限、原子的checkpointと再開、生成コード用の補助オラクルは未確認である。今回は文献と実装の対応確認を完了し、5,000件の本番再評価は開始していない。
