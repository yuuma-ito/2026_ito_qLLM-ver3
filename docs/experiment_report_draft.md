# Qiskitコード生成におけるモデルと介入条件の比較実験レポート 下書き

本研究では、3種類のOllamaモデルによるQiskit量子回路コード生成を対象に、タスク難度と介入条件による生成品質の違いを調べる。構文・実行・出力・構造を分けて評価し、成功率だけでなく、失敗類型、修正による救出、退行、生成に要したトークン数と時間を比較する。

<!-- auto:status:start -->
簡易実験は2回完了した。本実験は未検証であり、モデル間・難度間の比較に関する結論は、全件記録と検証後に確定する。
<!-- auto:status:end -->

<!-- auto:capture:start -->
集計時点：2026-10-08 21:58:27 JST。数値は最終更新時点の値であり、5分ごとに自動更新する。[集計スナップショット](experiment_report_snapshot.json)に同じ時点の件数と出典を保存する。
<!-- auto:capture:end -->

## 1 目的と比較の観点

量子回路コードの生成では、コードを実行できることと、期待する量子状態・測定分布を得られることを別に評価する必要がある。本実験では、初回生成の品質に加え、生成後の修正と生成前の注意事項の追加が、それぞれ評価結果をどの程度改善するかを検討する。

比較の観点は、モデルごとの生成品質、タスク難度による失敗の違い、介入条件によるbaseline失敗例の救出、介入によって成功例が失敗へ変わる退行、および品質と生成コストの関係である。APIヒントのablationおよび旧実験のH0〜H3・exp4は今回の対象に含めない。

## 2 実験方法

### 2.1 モデルと実行環境

対象は `qwen3.5:4b`、`gemma4:e4b-it-qat`、`qwen3.5:9b` の3モデルである。実験設定ではモデル名に `ollama:` を付けて記録する。モデルの同定にはタグに加え、保存されたサーバ情報のdigestと量子化情報を用いる。タグの数値だけをモデルの正確な総パラメータ数とはみなさない。

生成要求は共有OllamaのOpenAI互換APIへ逐次送信する。保存された環境情報は、Python 3.12.3、Qiskit 2.5.2、Qiskit Aer 0.17.2、OpenAI SDK 3.26.0である。簡易実験の事前確認で取得したOllamaバージョンは0.35.1であった。

### 2.2 タスクと試行数

本実験では以下の10タスクを使用する。難度区分はハーネスのタスク分類に従う。

| 難度 | タスク |
| --- | --- |
| easy | T1 Bell、T2 GHZ |
| medium | T3a Deutsch–Jozsa constant、T3b Deutsch–Jozsa balanced、T4 Bernstein–Vazirani 011、T5 Grover 11 |
| hard | T6 QFT 001、T7 IQFT 001、T8 QPE 001、T9 Ansatz 001 |

本実験の計画は、3モデル × 10タスク × 10 seed（0〜9）× 5条件 = 1,500レコードである。1レコードは1つのモデル・タスク・seed・条件の最終評価と修正履歴に対応する。修正roundを別のレコードとして数えない。

簡易実験はBellとDeutsch–Jozsa constantの2タスク、seed 0・1を対象とし、1回あたり3 × 2 × 2 × 5 = 60レコードを計画した。同じ設定で2回実行したが、seed集合も同じであり、新たなseedによる独立標本として合算しない。

### 2.3 比較条件

| 条件 | 手順 |
| --- | --- |
| baseline | 初回生成と評価を1回行う |
| self_refine | モデル自身の見直しによって修正する |
| execution_feedback | 評価器のエラーや実行結果を提示して修正する |
| self_debugging | 説明・原因分析・修正の手順によって修正する |
| preventive_spec | 生成前に共通の注意事項を追加して1回生成する |

baselineと修正型3条件は、同じモデル・タスク・base seedの初期生成コードと初期評価を共有する。これにより、初期生成の違いを抑えた対応付き比較を行う。修正は最大3回で、初期評価または修正後評価がL3成功に達した場合に修正を終了する。修正roundの生成seedは `base seed + round番号` とする。

preventive_specは異なる初期プロンプトから独立に生成するため、同じ初期コードを修正する条件とは性質が異なる。同じモデル・タスク・seedでbaselineと対応付けるが、改善を修正能力だけに帰属させない。

### 2.4 生成設定

| 項目 | 設定 |
| --- | --- |
| temperature | 0.7 |
| 最大修正回数 | 3 |
| reasoning_effort | none |
| max_tokens | 1回の生成要求につき1,024 |
| API timeout | 1回の生成要求につき600秒 |
| 同時生成要求 | 1 |
| pricing | 未設定 |

SDKの自動再送は無効である。旧本実験ではtimeout以外の初回要求エラーに対しseedを外した再要求を1回行っていた。今回の本実験では、Ollamaの接続障害に対し5・10・20・30・30秒待って最大5回再送し、プロンプト・temperature・seedを維持する。seed非対応を明示された場合だけseedを外して再送する。回復しない接続障害やtimeoutは記録して停止する。再試行回数は各round、回復方針はmanifestに記録する。旧本実験と今回の本実験は接続回復方針が異なるため、結果を別実験として比較する。

### 2.5 評価指標

| 指標 | 判定内容 |
| --- | --- |
| L0 | コードの実行・importが通り、引数なしで呼べる `build_circuit` が存在する |
| L1 | 回路を構築し、タスクのシミュレーション・状態評価を実行できる |
| L2 | 出力分布または状態ベクトルが期待値としきい値内で一致する |
| structure_match | 量子ビット数や、タスクに指定されたゲート数等の構造要件を満たす |
| L3 | L0・L1・L2・structure_matchがすべて真である |

L2は出力の正しさ、L3は利用可能な構造要件を含む総合成功を表す。`final_success` と `first_success_round` はL3に基づくため、L2成功率と混同しない。

測定分布タスクでは8,192 shotsによる分布と期待分布の全変動距離を用いる。状態ベクトルタスクでは大域位相を合わせたベクトル距離を用いる。各タスクのしきい値は0.05であり、距離がしきい値未満の場合にL2成功と判定する。生成回路に測定がない分布タスクでは評価用コピーへ測定を追加する。

### 2.6 失敗と介入効果の集計

`failure_stage` は失敗した段階、`error_category` は失敗原因を表す。例外型とメッセージも保存する。旧記録は生JSONLを保持したまま保存情報から分類を補い、元の原因分類を保持する。簡易実験2回では、それぞれbuild段階のimport失敗1件を `build_error` に整理したが、成功率・生成コード・評価値は変えていない。本実験のGHZ seed 6 self_debuggingの `result.counts` 誤用は `exec / interface_mismatch` であり、接続障害には含めない。[分類確認記録](ghz_seed6_failure_classification.json)に出典recordのハッシュとround別分類を保存した。

失敗は `syntax`、`import_error`、`interface_mismatch`、`build_error`、`qubit_count_mismatch`、`bit_order_error`、`wrong_output`、`unknown_error`、`api_timeout` に分類する。API障害の有無は、最終失敗類型だけでなく各roundの生成エラーとtimeoutも確認する。

介入の救出は、対応するbaselineがL2失敗、介入後がL2成功である場合とする。救出率の分母は対応するbaseline失敗例数とする。baseline退行は、baselineがL2成功、介入後がL2失敗である場合である。修正過程の悪化は、同じ修正条件内で最終段階点が初期段階点を下回る場合であり、baseline退行とは別に集計する。

API接続障害・timeoutはコード品質の失敗と区別して報告し、元の記録を保持する。API障害がある組を追試する場合は、同じモデル・タスク・seedの比較条件をそろえた別実験として記録し、元実験と追試の結果を分ける。

## 3 完了済みの簡易実験結果

2回とも予定60件を記録し、欠落・重複・予定外記録は0件であった。共有初期生成の対応関係を含むsanity checkと自動検証は成功し、API障害を含む記録は0件であった。以下の各セルは2タスク × 2 seedのL2成功件数／4件を示す。

### 簡易実験 1 のL2成功件数

| モデル | baseline | self_refine | execution_feedback | self_debugging | preventive_spec |
| --- | --- | --- | --- | --- | --- |
| qwen3.5:4b | 1/4 | 2/4 | 4/4 | 4/4 | 0/4 |
| gemma4:e4b-it-qat | 4/4 | 4/4 | 4/4 | 4/4 | 0/4 |
| qwen3.5:9b | 3/4 | 4/4 | 4/4 | 4/4 | 0/4 |

全条件合計は 42/60 件（70.0%）であった。この合計は異なる5条件の混合であり、baselineの成功率や介入効果の推定値ではない。

### 簡易実験 2 のL2成功件数

| モデル | baseline | self_refine | execution_feedback | self_debugging | preventive_spec |
| --- | --- | --- | --- | --- | --- |
| qwen3.5:4b | 1/4 | 2/4 | 4/4 | 4/4 | 0/4 |
| gemma4:e4b-it-qat | 4/4 | 4/4 | 4/4 | 4/4 | 0/4 |
| qwen3.5:9b | 3/4 | 4/4 | 3/4 | 4/4 | 0/4 |

全条件合計は 41/60 件（68.3%）であった。この合計は異なる5条件の混合であり、baselineの成功率や介入効果の推定値ではない。

### 3.3 簡易実験から確認できること

qwen3.5:4bでは、両実験ともbaselineが1/4件、self_refineが2/4件、execution_feedbackとself_debuggingがそれぞれ4/4件であった。この対象集合では、実行結果の提示と自己デバッグによってbaseline失敗3件が救出された。

gemma4:e4b-it-qatでは、baselineが両実験とも4/4件であり、修正型条件も4/4件であった。初期評価でL3成功の場合は修正を行わないため、この結果だけで修正能力が高いとは判断できない。

qwen3.5:9bでは、baselineが両実験とも3/4件であった。execution_feedbackは1回目が4/4件、2回目が3/4件であり、同じseed集合でも最終評価に差が生じた。その原因を生成の変動や測定の変動のどちらかに特定するには、対応するコードとround履歴の確認が必要である。

preventive_specは両実験とも0/12件で、baseline成功から失敗への退行がそれぞれ8件あった。ただし、これは2タスク・2 seed・現在の注意事項プロンプトに限定した結果であり、生成前介入一般の無効性を示すものではない。プロンプト変更を行う場合は別の実験条件として扱う。

<!-- auto:full-results:start -->
## 4 本実験の記録状況と暫定結果

2026-10-08 21:58:27（日本時間）時点で、予定1,500件のうち168件（11.2%）を記録した。残りは1,332件である。L2成功は70件、L2失敗は98件、API障害を含む記録は0件であった。重複は0件、予定外記録は0件であった。

本実験は未検証のため、以下の数値は暫定結果である。全件の記録とsanity check・API障害確認を終えるまで、最終結果として扱わない。

| モデル | 記録件数 | 予定件数 |
| --- | --- | --- |
| qwen3.5:4b | 168 | 500 |
| gemma4:e4b-it-qat | 0 | 500 |
| qwen3.5:9b | 0 | 500 |

### 条件別のL2とL3成功件数

| モデル | 条件 | 記録件数 | L2成功 | L3成功 | API障害を含む記録 |
| --- | --- | --- | --- | --- | --- |
| qwen3.5:4b | baseline | 34 | 4 | 4 | 0 |
| qwen3.5:4b | self_refine | 34 | 14 | 14 | 0 |
| qwen3.5:4b | execution_feedback | 34 | 23 | 23 | 0 |
| qwen3.5:4b | self_debugging | 33 | 27 | 27 | 0 |
| qwen3.5:4b | preventive_spec | 33 | 2 | 2 | 0 |

未完了のモデル・タスク・条件には件数の偏りがある。途中データからモデル全体の優劣を判断しない。

### タスク別の記録件数

| タスク | 記録件数 |
| --- | --- |
| T1_Bell | 50 |
| T2_GHZ | 50 |
| T3a_DJ_constant | 50 |
| T3b_DJ_balanced | 18 |
| T4_BV_011 | 0 |
| T5_Grover_11 | 0 |
| T6_QFT_001 | 0 |
| T7_IQFT_001 | 0 |
| T8_QPE_001 | 0 |
| T9_Ansatz_001 | 0 |

### 最終評価の類型別件数

| 類型 | 件数 |
| --- | --- |
| build_error | 12 |
| import_error | 74 |
| interface_mismatch | 4 |
| ok | 70 |
| syntax | 3 |
| wrong_output | 5 |

API障害を含む記録件数はround履歴も確認した値であり、最終評価の失敗類型とは別の集計である。API障害がある場合は、元結果を保持し、対応条件をそろえた追試を別実験として報告する。
<!-- auto:full-results:end -->

## 5 考察

簡易実験では、qwen3.5:4bのbaseline失敗例に対して実行結果フィードバックと自己デバッグによる救出が観測された。これは、初回生成で失敗したコードでも修正によって期待出力へ到達し得ることを示す。一方、初期成功例では修正自体が行われないため、条件別の成功率だけでは修正手法の能力を比較できない。baseline失敗例を対象とした救出率を併記する必要がある。

生成前の注意事項追加では成功率の低下が観測された。原因の検討では、注意事項の長さ、出力コードの変化、import・インターフェース・回路ロジックの失敗を分けて確認する。今回の観測だけから、いずれかが原因であるとは断定しない。

本実験の考察では、モデル・タスク・seedを対応付けた成功率差と救出・退行を調べ、必要な生成時間やトークン数も併せて比較する。修正回数が増えることで品質が改善した場合でも、追加コストとの関係を示す。

## 6 限界

簡易実験は各モデル・条件につき4件であり、難タスクを含まない。2回の実行は同じseed集合を使用しているため、反復結果を独立標本として扱った統計的な有意差は主張しない。本実験でも同じ初期コードを共有する条件の記録は独立ではない。

構造評価はタスクに定義されたoracleの範囲に限られ、すべてのゲート種・深さ・測定要件を完全に検証するものではない。bit_order_errorは分布のビット反転比較に基づく判定である。

分布評価は有限shotsを用い、現行評価器ではシミュレータseedを固定していない。モデルへのseed指定だけでは、再評価まで含めた完全な再現性は保証されない。

生成長は1回1,024 tokensに制限される。API障害や生成長の上限による影響をモデルの量子回路ロジック能力と混同しない。共有サーバ上の経過時間は他の負荷の影響を受け得る。

条件別のトークン数と経過時間には共有初期生成の値が含まれるため、全条件の値を単純に合計すると初期生成を重複計上する。実際のAPI総使用量とは分けて解釈する。pricing未設定の金銭コストは未算出であり、0円とは扱わない。

## 7 本実験完了後に追記する内容

- 全1,500レコードの整合性確認と、自動検証・API障害確認の結果。
- モデル × 条件のL2・L3成功率、およびタスク別・難度別の件数と成功率。
- baseline失敗類型別の救出率、baseline退行、修正過程の悪化。
- 成功に至ったround、生成時間、トークン数、コード行数、ゲート数、回路深さ。
- API障害の元結果と、実施した場合の対応条件をそろえた追試結果。
- 対応付きデータと標本数に適した不確実性の評価、および代表的な成功・失敗例の分析。

## 8 再現用設定と根拠ファイル

実験方法は[本実験設定](../configs/full_all_models.json)、[簡易実験設定](../configs/shared_three_models_quick.json)、[実行処理](../scripts/run_experiment.py)、[修正処理](../harness/runner.py)、[評価器](../harness/evaluator.py)、[APIクライアント](../harness/llm_clients.py)に対応する。旧モデル名が残る[新ハーネス仕様](new_harness_spec.md)よりも、今回のモデル構成については実験ごとの保存設定を優先する。

- 簡易実験1：[保存設定](../results/shared_three_models_quick_20261007T123904531170Z/experiment_config.json)、[条件別集計](../results/shared_three_models_quick_20261007T123904531170Z/summary_by_condition.csv)、[救出率](../results/shared_three_models_quick_20261007T123904531170Z/rescue_rates_by_error.csv)、[baseline退行](../results/shared_three_models_quick_20261007T123904531170Z/baseline_regressions.csv)、[sanity report](../results/shared_three_models_quick_20261007T123904531170Z/sanity_report.json)、[自動検証](../results/shared_three_models_quick_20261007T123904531170Z/automation_report.json)、[manifest](../results/shared_three_models_quick_20261007T123904531170Z/manifest.json)。
- 簡易実験2：[保存設定](../results/shared_three_models_quick_20261007T123904532290Z/experiment_config.json)、[条件別集計](../results/shared_three_models_quick_20261007T123904532290Z/summary_by_condition.csv)、[救出率](../results/shared_three_models_quick_20261007T123904532290Z/rescue_rates_by_error.csv)、[baseline退行](../results/shared_three_models_quick_20261007T123904532290Z/baseline_regressions.csv)、[sanity report](../results/shared_three_models_quick_20261007T123904532290Z/sanity_report.json)、[自動検証](../results/shared_three_models_quick_20261007T123904532290Z/automation_report.json)、[manifest](../results/shared_three_models_quick_20261007T123904532290Z/manifest.json)。
- 旧本実験：[保存設定](../results/shared_three_models_full_20261007T145103982885Z/experiment_config.json)、[manifest](../results/shared_three_models_full_20261007T145103982885Z/manifest.json)。1,500件を記録したが、接続障害738件と未分類の評価エラー8件があり、検証で停止した。比較用の元結果として保持する。
- 今回の本実験：[保存設定](../results/shared_three_models_full_20261008T103231611899Z/experiment_config.json)、[manifest](../results/shared_three_models_full_20261008T103231611899Z/manifest.json)。接続回復対策を適用し、同じ3モデル・10タスク・10 seed・5条件で全1,500件を新規生成する。本文の本実験結果表は今回の実験を対象とする。途中集計と旧本実験は[スナップショット](experiment_report_snapshot.json)を参照する。未完了・未検証の結果は暫定とし、元のraw.jsonlは公開対象に含めない。

新しい本実験を実行するコマンドは以下である。

```bash
.venv/bin/python -m scripts.automate_experiment --config configs/full_all_models.json --new-run
```

実行済みの時刻付き実験を再開する場合は、対象ディレクトリの `experiment_config.json` を指定し、`--new-run` を付けない。実行中の同じ実験を重ねて開始しない。
