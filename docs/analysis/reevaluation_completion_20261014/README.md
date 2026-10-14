# 再評価の残る準備条件の解消

2026-10-14。判定は **GO：主評価v4による保存コードの再採点、補助は別列、基盤障害時は停止**。前回の[CONDITIONAL GO](../reevaluation_readiness_20261014/README.md)で残した実行計画・資源適合の確認・6タスクの補助実装を追加した。**本番5,000件は開始していない。** GOは全ての生成コードの正当性や資源適合の証明ではなく、障害を安全に検出・記録・停止できる条件を満たした準備判定である。

過去の文献監査、再点検、10記録の試験はそのまま保持した。新しい補助版は`coherent_oracles_v2`。主判定`evaluation_policy_v4`、距離/TVDの閾値、shot/seed、元5,000件の判定・raw・設定・固定発表資料は変更していない。新しいprofileで別checkpointを使い、v1の結果へ追加・混在しない。

## 解消した条件

| 条件 | 実装・検証 | 結果 |
| --- | --- | --- |
| 全件の実行計画 | `harness/reevaluation_plan.py:build_plan`。固定snapshotと保存設定から予定keyを生成し、出典hash、全記録・round・最終コード・code hashを照合 | 5,000記録・9,517 round、欠落・重複key・予定外記録0 |
| 全件処理の停止・再開 | `execute_bounded_batch`。全計画を同一checkpointに固定し、明示された最大48 roundだけを処理。基盤失敗を保存した直後に停止し、以後の再開も拒否 | 故障注入では1件目のCPU失敗で停止、2件目は未実行。再開も追加実行0 |
| 保存コードの資源適合 | 全件のコードサイズと旧回路メタデータを静的確認。全10タスク・5モデルの20記録・58 roundを隔離試験 | 基盤失敗・timeout・policy拒否・memory不足0。再開0実行。未実行コードの適合は断定しない |
| 残る6タスクの補助 | DJ constant/balanced、BV、Grover、QPE、Ansatzの期待状態・変換をNumPyの式から構成 | 既知の正解・不正解、全体位相、手計算・別の振幅更新と一致 |

主成功率と補助成功率は合成しない。補助stateとtransformも別の意味である。主が成功し、変換補助が失敗した場合も主L3を保持し、診断を別列に残す。

## 全件計画と見つかった旧保存形式

[full_plan_manifest.json](full_plan_manifest.json)に出典・設定・評価器profile・全計画digestを、[full_case_catalog.csv](full_case_catalog.csv)に全9,517 roundの条件key・code hash・旧判定・行番号を保存した。生成コード・生出力・例外文は含まない。カタログの全列を元の計画と照合し、digestは`2e2186ce8474eb6e48c5423940e8421235c3e686074b9e152661fc51014a4a1b`。

| 出典 | 記録数 | 用途 |
| --- | ---: | --- |
| `shared_three_models_full_20261008T103231611899Z` | 1,500 | 3モデル、seed 0〜9 |
| `shared_five_models_full_20261010T041019864060Z` | 2,500 | 5モデル、seed 10〜19 |
| `shared_two_models_seed0_9_full_20261012T100658266051Z` | 1,000 | 2モデル補完、seed 0〜9 |

初回の厳密なhash検査は、3モデル出典のraw行210・round0で失敗した。抽出コードが空文字で、保存済みhashも空文字だったためである。**この組だけ**旧形式のhash欠落として扱い、計算済み空コードhashと旧hash欄を別記する修正を行った。コードが非空、または保存hashが非空の不一致は従来通り拒否する。rawも旧hash欄も書き換えない。空コードはモデルのinterface評価対象として計画に残す。

静的構文解析では715 roundがSyntaxErrorだった。これもモデルの評価対象であり、計画の破損やAPI障害として除外しない。コード最大4,736 bytes、全round合計10,727,045 bytesで、1 MiBの入力上限を超える例は0。旧最終記録の最大量子ビット数4、全roundの最大記録ゲート数40で、sandboxの8 qubits・10,000操作上限を超える記録も0。[旧メタデータ確認](resource_static_metadata.json)は**過去の観測値**であり、新しい実行の資源上限を証明する値ではない。

`build_plan`は生成コードを実行しない。`execute_bounded_batch`はcase keyを明示する必要があり、全件の自動実行loopを持たない。全体の一意key・profile・出典を固定するcheckpointのまま、次回以降も明示したbatchを処理できる。本番着手の別指示を受けるまで、本番用batchを実行しない。

## 補助オラクルの式と適用範囲

`harness/supplementary.py:reference_operator`はQiskitやtask mockを呼ばず、タスクの指定式から期待変換Vを作る。state補助の期待値は`V|0…0〉`。実際の回路は密度行列で取得し、`F=〈ψ|ρ|ψ〉`と純度を診断する。unitaryの場合のtransform補助は、全基底と基底0を全列へ結ぶ実・虚の重ね合わせで比較する。

| タスク | 独立した期待状態・変換の構成 | transform入力数 | 限界 |
| --- | --- | ---: | --- |
| DJ constant | `∣00〉⊗∣−〉`（ancillaは高位q2）。X ancilla、H全体、identity oracle、H入力の積 | 22 | constant 0という固定関数だけ |
| DJ balanced | `∣11〉⊗∣−〉`。oracleは2つのCNOTを基底indexの置換で表現 | 22 | `x0 XOR x1`だけ。balanced関数一般ではない |
| BV | `∣011〉⊗∣−〉`。同じ置換oracleと入力H、4 qubitsのKronecker積 | 46 | hidden string 011だけ |
| Grover | `∣11〉`。`D=2∣s〉〈s∣−I`、`O=diag(1,1,1,−1)`、`V=DO(H⊗H)` | 10 | 2 qubits・1 marked・1 iterationだけ。diffusionの共通全体位相は許容 |
| QPE | `∣1010〉`。countingのH、eigenvalue kickbackの対角位相、負符号DFT、eigenstate Xを積で構成 | 46 | theta=π/2、3 count bits、eigenstate ∣1〉だけ |
| Ansatz | `RY1(π/5) RY0(π/6) CX01 RY1(π/3) RY0(π/4)`を小行列の積と置換で構成 | 10 | 指定角だけ。任意のパラメータ族を保証しない |

新しいstate補助の距離基準0.05は独自の状態基準であり、distributionタスクのTVD=0.05をfidelityへ換算したものではない。正規化純粋状態の全体位相を合わせた距離に対する厳密換算`F > 0.9975015625`を使う。混合状態は`diagnostic_only`とし、この換算を適用しない。transformも純粋入力・unitaryに限定し、process fidelityは診断値である。主判定のTVDとは分離する。

measurementを含む回路や幅違いはstate/transform補助の適用外とし、測定を勝手に削除しない。非ユニタリではstate診断ができてもunitary transformは適用外となる場合がある。有限閾値でprobeを通ったことから、全入力の最悪距離・diamond norm・全アルゴリズムの正当性は保証しない。

## テストと資源適合試験

**全324テスト成功、失敗・error・skipは0、Qiskitの非推奨警告44件。** 今回の追加15テストは[tests/test_reevaluation_completion.py](../../../tests/test_reevaluation_completion.py)。全体テスト成功の確認日時とprofileは[verification_results.json](verification_results.json)に記録し、その後に保存コードを試験した。

| 検査 | テスト名 | 不正ケースと成功条件 |
| --- | --- | --- |
| 6タスクの既知正誤 | `test_six_auxiliary_oracles_known_correct_wrong_and_global_phase` | 各mockの正解／不正解を別の式で識別。全体位相を変えても同じ判定 |
| DJ/BV相対位相 | `test_ancilla_phase_reference_matches_hand_state` | 手書き2振幅に一致。同じ計算基底分布のancilla ∣+〉は不合格 |
| Grover/QPE基底 | `test_qpe_and_grover_references_match_exact_basis_states` | 正しい基底indexの振幅絶対値1、他の確率約0 |
| Ansatz | `test_ansatz_reference_matches_independent_amplitude_updates` | 行列積とは別の振幅更新loopに一致 |
| 計画破損 | `test_full_plan_missing_duplicate_hash_and_config_corruption` | 欠落・重複・非空コードhash不一致を拒否 |
| 基盤失敗で停止 | `test_bounded_scheduler_stops_on_runtime_failure_and_cannot_silently_resume` | CPU失敗1件を保存して停止。後続を実行せず、同じcheckpointで再開しても停止 |
| scheduler統合 | `test_bounded_scheduler_synthetic_integration_and_resume` | 合成保存コード2件を実際に隔離実行し、再開は0実行 |
| 空コードの旧形式 | `test_legacy_empty_code_has_explicit_missing_hash_provenance` | 計算hashと旧空欄を区別し、元データを保持 |

資源適合試験は、各taskで旧最終成功の中から最長コードの記録を選び、旧失敗側もモデルの網羅と長いコードを優先して選んだ。無作為標本ではない。選択は[成功側](resource_selection_positive.json)・[失敗側](resource_selection_negative.json)、結果は[成功側21 round](resource_positive_report.json)・[失敗側37 round](resource_negative_report.json)、比較は[resource_comparison.csv](resource_comparison.csv)。

全10task・5モデル、20記録・58 roundが完了。壁時計約65.23秒、子CPU合計約62.12秒。最大builder壁時計約0.78秒、最大oracleまたは失敗段階の壁時計約1.07秒で、各段階25秒・CPU15秒／hard16秒・address space 2 GiBの制限内で完了した。メモリのpeak RSSを測ったとは主張しない。両方を[再開](resource_positive_resume.json)・[再開](resource_negative_resume.json)し、追加実行はいずれも0。元出典hashも不変。[sanity_report.json](sanity_report.json)に全件計画と試験の整合を記録した。

基盤障害・欠落・重複keyは0。モデル結果はok 17、import_error 6、interface_mismatch 2、build_error 10、syntax 14、wrong_output 9 round。補助はpass 16、fail 9、適用外33 roundで、適用外を成功へ含めない。追加LLM要求・LLM費用は0。本番の処理時間・成功率・モデルの優劣へこの標本から単純外挿しない。

### 固定出力と変換全体の相違

成功側のQPE最終roundとAnsatz初回roundはstate補助がpass、transform補助がfailだった。QPEは主も成功であり、指定固定入力の測定出力一致だけでは変換全体を識別できない例となる。Ansatzの保存履歴では後続roundはstate/transformともpassした。ただし旧feedbackで選ばれたコードの診断であり、新しい補助による介入効果とは扱わない。

成功側DJ constantの最終コードには測定が含まれ、主は成功でも補助は適用外だった。主の測定許容仕様と、補助が検査する未測定状態・unitaryの範囲の違いである。測定を削除して補助成功を作る修正はしていない。

## 参考資料と今回の独自設計

原文PDF取得証拠・節・ページは[前回のsource receipts](../literature_reliability_20261014/source_implementation_recheck/source_receipts.json)を参照する。Abreuらは引き続き原文未確認で、実装根拠に使わない。今回、文献がこの6つの数式・probe数・資源値を指定したとは主張しない。

| 根拠 | 確認済み記述から採用する論点 | 今回への適用 |
| --- | --- | --- |
| [Paltenghi & Pradel §4.1 p.8、§4.3 pp.12–13、§7.2 p.27](https://arxiv.org/pdf/2410.00650v1) | 入力生成、距離・同値性、mutationによる検証 | 指定アルゴリズムの式、複数入力と既知変異を今回独自に設計 |
| [Barr et al. §2.3 p.4、§5 p.9](https://discovery.ucl.ac.uk/id/eprint/1471263/1/06963470.pdf) | 健全性・完全性、部分オラクル | state/transform/適用外を分離。テストだけで一般的な完全性を主張しない |
| [Qiskit state_fidelity / process_fidelity](https://qiskit.qotlabs.org/docs/api/qiskit/quantum_info) | pure targetならfidelityはdensityの期待値、状態とチャネルの指標の違い | 数式で期待値を構成し、installed Qiskit 2.5.2・Aer 0.17.2のAPIと照合 |
| [DensityMatrix.from_instruction](https://qiskit.qotlabs.org/docs/api/qiskit/qiskit.quantum_info.DensityMatrix) | 回路から密度行列を取得するAPI | 非ユニタリを純粋状態1分岐へ置換しない。installed signature・ソースhashは[installed_oracle_spec.json](installed_oracle_spec.json) |
| [Chen et al. §2.3 p.4](https://arxiv.org/pdf/2107.03374) | 生成コードを隔離する実行環境 | 前回実装のLandlock/seccompを維持。今回の停止条件・checkpoint・上限は独自設計 |
| [Madaan et al. Algorithm 1 p.3 / Eq.4 p.4](https://arxiv.org/pdf/2303.17651v2) | 最終出力と履歴 | 旧feedback履歴を保持し、新しい介入の効果と混同しない |

原文のこれらの箇所は**原文確認済み**、全計画・停止処理・6補助は**実装確認済み**、指定した既知ケースと故障注入は**独立検証済み**。未実行コード全部の資源適合、native/kernelの未知の欠陥に対する安全性、任意パラメータ族・任意アルゴリズムの完全性は**未確認**として残す。期待値の構成は主評価から独立だが、実際の回路実行はQiskitを共有する。

## GOの適用条件と本番着手前の扱い

準備上の未実装条件は解消した。以下は本番運用の仕様と既知の科学的限界であり、これを削除して無条件の安全性・妥当性を主張しない。

- 同じ全計画・profileで、明示した最大48 roundのbatchを処理する。既存結果と混ぜず、checkpointは原出典とは別に保存する。
- timeout、resource、crash、protocol、policy failureはモデルの誤答へ算入せず停止する。同じcheckpointで失敗を飛ばして後続へ進めない。対処後は新profile/checkpointを使い、旧結果を保持する。
- `not_applicable`・混合状態診断・transform失敗を区別し、主L3は出力一致＋従来の粗い構造条件として解釈する。補助を主判定へ採用する変更は別途仕様・比較が必要。
- 未実行コード全ての適合は、全件を実行しない限り実測できない。静的確認・代表的な長いコードの試験・失敗時停止を着手条件とする。全件終了後は改めて欠落・重複・基盤障害・L0〜L3・初成功／最終成功・出典hashを検証する。
- 有限shot、閾値近傍、旧feedbackによる選択、同一初期共有、task/seedの相関、Qiskitスタックの共通依存、Linux policyのnative/kernel残存リスクは保持する。5,000件を独立二項試行とした統計区間やSelf-Refine原論文の完全再現を主張しない。

本番着手の指示はまだ受けていないため、5,000件は実行しない。Git pushも行わない。
