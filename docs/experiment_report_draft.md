# Qiskitコード生成におけるモデルと介入条件の比較実験レポート 下書き

本研究では、OllamaモデルによるQiskit量子回路コード生成を対象に、初期生成で失敗したコードを各介入がどの程度救済できるかを調べる。現行の主要分析には、検証済み3実験の計5,000条件記録に整備後の評価と必要な部分追試を反映し、共通の初期失敗を分母としたR・F・Dの救済率を用いる。元実験の出典・設定差は保持する。Pは独立生成として改善・悪化を別に扱う。以下の旧実験表と過去の分析は当時の記録であり、現行値は冒頭の主要結果とリンク先を参照する。

<!-- intervention-rescues:20261015:start -->
## 現行の主要結果：介入による初期失敗の救済

本研究の主要評価指標は、初期生成で失敗したコードに対する介入の救済率である。評価方法の整備は妥当な判定のための手続きとして扱い、評価器間の比較を研究の主題には置かない。

集計UTC：2026-10-15T15:03:26.698613+00:00。5モデル・10タスク・seed 0〜19の1,000初期組（5,000条件記録）で、初期成功455組、初期失敗545組。R・F・Dは同じ初期コードと判定を共有する。救済率の分母は新評価での初期失敗545組とし、最大3修正後の成功を数える。

| 介入 | 救済数／初期失敗 | 救済率 |
| --- | ---: | ---: |
| R | 96/545 | 17.6% |
| F | 183/545 | 33.6% |
| D | 180/545 | 33.0% |

R＝自己見直し、F＝実行結果提示、D＝自己デバッグ。

FとDの共通救済140組、Fのみ43組、Dのみ40組、双方未救済322組。全体の救済率は近いが、救済対象とモデル別の大小は異なる。観測値の差を一般的な優劣や統計的有意差として扱わない。

P（生成前注意事項）は独立生成であり、修正型と分ける。baseline初期失敗に対応する成功124/545組、baseline初期成功に対応する失敗106/455組を併記する。

[モデル・タスク・初期失敗類型・修正回数別の結果](analysis/intervention_rescues_20261015/README.md)、[解釈と次の分析](analysis/intervention_rescues_20261015/findings.md)、[固定スナップショット](analysis/intervention_rescues_20261015/results_snapshot.json)を参照。

主L3はevaluation_policy_v4を採用し、保存経路と必要な部分追試の結果を反映した。全件を新評価器で初回生成からやり直した実験ではない。出典・設定差と経路の由来は詳細資料へ保存する。

以下の旧実験表・過去の分析節は当時の評価での記録として保持する。現在の救済率の引用には上記の固定集計を用い、旧分母・旧救済数・旧コスト分析を現行値と組み合わせない。
<!-- intervention-rescues:20261015:end -->

<!-- reachable-rescues:20261016:start -->
## 現行経路の全履歴・追加コスト（2026-10-16）

Fのみ43組・Dのみ40組の全83組、両条件166履歴・398修正遷移を確認した。分岐後の旧suffixを除外し、各record・round・コードhash・由来と静的変更を公開CSVで追跡できる。import/API、回路構築、量子論理、測定/出力取得の変更は観察注記であり、成功原因の認定ではない。

共有初期生成を除き未救済への消費も含む追加tokens/救済はR 18,852.6、F 9,333.8、D 10,976.6。生成要求秒/救済はR 911.1、F 444.2、D 553.6。保存prefixの記録値と新suffix実測値の合算は再構成経路の計算値であり、全件新実験の実測コストや実測の費用削減とは呼ばない。金銭費用は未測定。Pは独立生成として別集計。

3回目の追加救済はR 19/468組、F 28/390組、D 33/398組。3回目の追加tokensはR 559,141、F 491,676、D 588,970。2回で区切ると3回までに救済できたうちR 19.8%、F 15.3%、D 18.3%を失う。同一履歴の打切りであり、上限別独立実験でも一般的最適性の根拠でもない。

[全分析・再実行手順](analysis/reachable_rescues_20261016/README.md)、[考察](analysis/reachable_rescues_20261016/findings.md)、[固定発表出典](presentation_sources/20261016T_reachable_rescues/README.md)を参照。モデル・タスク/難度・初期失敗類型・元実験・seedブロックの分母を保持した。研究の主題は介入による救済であり、評価器比較ではない。旧数値は過去の記録として以下に保持する。
<!-- reachable-rescues:20261016:end -->

<!-- auto:status:start -->
簡易実験は2回完了した。3モデル本実験は全件記録と自動検証が完了した。モデル間・難度間の比較の考察は、検証済み結果に基づいて追記する。追加・補完実験も全件記録と検証が完了した。元実験の内訳を保持し、seed 0〜19の固定時点の統合集計にはフィードバック処理差を併記する。
<!-- auto:status:end -->

<!-- auto:capture:start -->
集計時点：2026-10-16 00:00:06 JST。数値は最終更新時点の値であり、60分ごと（毎時0分）に自動更新する。[集計スナップショット](experiment_report_snapshot.json)に同じ時点の件数と出典を保存する。
<!-- auto:capture:end -->

## 1 目的と比較の観点

量子回路コードの生成では、コードを実行できることと、期待する量子状態・測定分布を得られることを別に評価する必要がある。本実験では、初回生成の品質に加え、生成後の修正と生成前の注意事項の追加が、それぞれ評価結果をどの程度改善するかを検討する。

比較の観点は、モデルごとの生成品質、タスク難度による失敗の違い、介入条件によるbaseline失敗例の救出、介入によって成功例が失敗へ変わる退行、および品質と生成コストの関係である。APIヒントのablationおよび旧実験のH0〜H3・exp4は今回の対象に含めない。

## 2 実験方法

### 2.1 モデルと実行環境

検証済み主分析の対象は `qwen3.5:4b`、`gemma4:e4b-it-qat`、`qwen3.5:9b` の3モデルである。`qwen2.5-coder:7b` と `gemma3:4b` を加えた5モデル追加実験は別実験ID・別保存先で完了した。実験設定ではモデル名に `ollama:` を付けて記録する。モデルの同定にはタグに加え、保存されたサーバ情報のdigestと量子化情報を用いる。タグの数値だけをモデルの正確な総パラメータ数とはみなさない。

生成要求は共有OllamaのOpenAI互換APIへ逐次送信する。保存された環境情報は、Python 3.12.3、Qiskit 2.5.2、Qiskit Aer 0.17.2、OpenAI SDK 3.26.0である。簡易実験の事前確認で取得したOllamaバージョンは0.35.1であった。

#### サーバのモデル一覧（ユーザー提示値）

| モデル | パラメータ数・量子化 | サイズ | 生成速度 | 導入時期 | 研究上の位置付け |
| --- | --- | --- | --- | --- | --- |
| `qwen2.5-coder:7b` | 7B・Q4_K_M | 4.7 GB | 8.0 tok/s | 今回 | 中間発表の予備実験モデル |
| `gemma3:4b` | 4B | 3.3 GB | 12.2 tok/s | 今回 | 中間発表の予備実験モデル |
| `qwen3.5:9b` | 9.7B・Q4_K_M | 6.6 GB | 6.0 tok/s | 10/4 | 現在の本実験 |
| `qwen3.5:4b` | 4.7B・Q4_K_M | 3.4 GB | 9.7 tok/s | 10/4 | 現在の本実験 |
| `gemma4:e4b-it-qat` | 7.5B・Q4_0（画像・音声入力つき） | 6.1 GB | 未測定 | 10/4 | 現在の本実験 |

出典はユーザー提示のモデル一覧であり、提示値をそのまま保持している。別途SF3のモデル一覧を取得し、5モデルの存在とdigest・量子化情報を確認した。[SF3取得記録](sf3_model_inventory_20261008.json)では、qwen2.5-coder:7bのパラメータ表記は7.6B、gemma3:4bは4.3B・Q4_K_Mであり、元の提示表と区別する。生成速度の測定条件（入力長、出力長、同時負荷、モデルのロード状態など）は未記載のため、参考値として扱い、本実験のround別実測値とは分ける。gemma3の量子化方式は未記載、gemma4の速度は未測定である。導入時期の「今回」「10/4」は提示表の表記を保持した。[モデル情報の保存記録](model_inventory_20261008.json)に出典区分を保存する。

旧2モデルがサーバに追加されたとの報告は、中間発表との比較を再検討する際に利用できる。ただし、前回の本実験は保存設定どおり3モデル・1,500件で完了し、旧2モデルを含む5モデルの追加実験を別記録として完了した。

追加実験として、旧2モデルを含む5モデル比較を別実験IDで完了した。対象は `qwen2.5-coder:7b`、`gemma3:4b`、`qwen3.5:4b`、`gemma4:e4b-it-qat`、`qwen3.5:9b` である。標準設定 `configs/shared_five_models_full.json` は10タスク・seed 0〜9・5条件で合計2,500件を予定する。ただし、保存設定ではseedを10〜19へ変更しており、実際の収集条件はこの保存設定に従う。全件検証済みであり、出典別結果と診断文処理差を保持して扱う。動作確認用の設定は `configs/shared_five_models_quick.json`（100件）である。旧2モデルの中間発表時の結果と比較する際は、ハーネスや条件の違いを明記する。

### 2.2 タスクと試行数

本実験では以下の10タスクを使用する。難度区分はハーネスのタスク分類に従う。

| 難度 | タスク |
| --- | --- |
| easy | T1 Bell、T2 GHZ |
| medium | T3a Deutsch–Jozsa constant、T3b Deutsch–Jozsa balanced、T4 Bernstein–Vazirani 011、T5 Grover 11 |
| hard | T6 QFT 001、T7 IQFT 001、T8 QPE 001、T9 Ansatz 001 |

検証済み3モデル本実験は、3モデル × 10タスク × 10 seed（0〜9）× 5条件 = 1,500レコードをすべて記録済みである。保存済みの追加実験は、5モデル × 10タスク × 10 seed（10〜19）× 5条件 = 2,500レコードを記録した。標準5モデル設定のseed 0〜9と、保存設定のseed 10〜19を区別する。1レコードは1つのモデル・タスク・seed・条件の最終評価と修正履歴に対応する。修正roundを別のレコードとして数えない。

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

L0〜L3は独立した点数ではなく、段階的な到達水準として扱う。L1達成にはL0達成を要し、L2達成はL0およびL1を満たしたうえで出力が所定の許容誤差内で期待値と一致した場合を意味する。L3達成は、さらにタスクに定義された構造要件を満たした場合を意味する。各水準の達成率は、同じ評価対象の全件数を分母とし、前段階の達成を含む累積的な割合である。

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
## 4 3モデル本実験の検証済み結果

実験ID：`shared_three_models_full_20261008T103231611899Z`。保存先：`results/shared_three_models_full_20261008T103231611899Z/`。

2026-10-16 00:00:06（日本時間）時点で、予定1,500件のうち1,500件（100.0%）を記録した。残りは0件である。L2成功は839件、L2失敗は661件、API障害を含む記録は0件であった。重複は0件、予定外記録は0件であった。

自動検証とsanity checkが成功し、API障害を含む記録はなかった。

| モデル | 記録件数 | 予定件数 |
| --- | --- | --- |
| qwen3.5:4b | 500 | 500 |
| gemma4:e4b-it-qat | 500 | 500 |
| qwen3.5:9b | 500 | 500 |

### 条件別のL2とL3成功件数

| モデル | 条件 | 記録件数 | L2成功 | L3成功 | API障害を含む記録 |
| --- | --- | --- | --- | --- | --- |
| qwen3.5:4b | baseline | 100 | 15 | 15 | 0 |
| qwen3.5:4b | self_refine | 100 | 33 | 33 | 0 |
| qwen3.5:4b | execution_feedback | 100 | 56 | 56 | 0 |
| qwen3.5:4b | self_debugging | 100 | 57 | 57 | 0 |
| qwen3.5:4b | preventive_spec | 100 | 11 | 11 | 0 |
| gemma4:e4b-it-qat | baseline | 100 | 65 | 65 | 0 |
| gemma4:e4b-it-qat | self_refine | 100 | 82 | 82 | 0 |
| gemma4:e4b-it-qat | execution_feedback | 100 | 87 | 87 | 0 |
| gemma4:e4b-it-qat | self_debugging | 100 | 88 | 88 | 0 |
| gemma4:e4b-it-qat | preventive_spec | 100 | 32 | 32 | 0 |
| qwen3.5:9b | baseline | 100 | 59 | 59 | 0 |
| qwen3.5:9b | self_refine | 100 | 73 | 73 | 0 |
| qwen3.5:9b | execution_feedback | 100 | 76 | 76 | 0 |
| qwen3.5:9b | self_debugging | 100 | 80 | 80 | 0 |
| qwen3.5:9b | preventive_spec | 100 | 25 | 25 | 0 |

### タスク別の記録件数

| タスク | 記録件数 |
| --- | --- |
| T1_Bell | 150 |
| T2_GHZ | 150 |
| T3a_DJ_constant | 150 |
| T3b_DJ_balanced | 150 |
| T4_BV_011 | 150 |
| T5_Grover_11 | 150 |
| T6_QFT_001 | 150 |
| T7_IQFT_001 | 150 |
| T8_QPE_001 | 150 |
| T9_Ansatz_001 | 150 |

### 最終評価の類型別件数

| 類型 | 件数 |
| --- | --- |
| build_error | 98 |
| import_error | 188 |
| interface_mismatch | 76 |
| ok | 839 |
| syntax | 116 |
| wrong_output | 183 |

API障害を含む記録件数はround履歴も確認した値であり、最終評価の失敗類型とは別の集計である。API障害がある場合は、元結果を保持し、対応条件をそろえた追試を別実験として報告する。
<!-- auto:full-results:end -->

### 再分類・再検証と主分析の範囲

現時点の確定結果および主分析対象は `shared_three_models_full_20261008T103231611899Z` の1,500/1,500件である。欠落・重複・予定外記録・API障害は各0件、L2成功は839件（55.93%）、sanity check・自動検証は成功し、unknown_errorは再分類済みである。5モデル追加実験を主分析に含めるかどうかは完了・検証後に判断する。保存済み検証で停止対象だった8記録は、Qiskit APIの誤用による7件の最終失敗と、途中で失敗した後に成功した1件だった。最終結果7件とround履歴21件の `unknown_error` を `exec / interface_mismatch` に再分類し、例外型と元メッセージを保存した。既存の分類規則に合わせ、build内のimport失敗も最終結果7件・round履歴19件を `build / build_error` に整理した。

元データは `raw.before_reclassify.jsonl` にバックアップした。追加生成・生成コードの再実行・再評価は行わず、分類情報以外の保存フィールドとエラーメッセージが一致することを照合した。L0/L1/L2/structure_match/L3は最終roundと一致し、L2成功839件（55.93%）を維持した。欠落・重複・予定外記録・API障害・最終結果とround履歴の未分類エラーはいずれも0件で、sanity checkと自動検証が成功した。preventive_specの300記録はすべて1回生成だった。

救出237件、修正過程の悪化41件、baseline退行93件を別々のCSVとして集計した。これらは異なる定義の集計であり、互いに排他的な失敗分類ではない。検証は記録・分類・集計の整合性を確認したもので、保存済み評価値を新たに実行して確かめたものではない。タスクoracle、10 seed、生成長上限など既述の評価範囲は維持する。[再分類・再検証記録](../results/shared_three_models_full_20261008T103231611899Z/reclassification_report.json)に変更一覧、バックアップと再分類後データのSHA-256、CSVのSHA-256を保存した。

旧本実験 `shared_three_models_full_20261007T145103982885Z` はAPI接続障害738件（gemma4 238件、qwen3.5:9b 500件）を含み、生成の可用性とコード品質を混同するため主分析から除外する。元データは変更せず、接続障害の参考記録として保持し、主分析への合算やモデル能力の直接比較には使わない。

## 5モデル追加実験の進捗

実験IDは `shared_five_models_full_20261010T041019864060Z`。標準の `configs/shared_five_models_full.json` を基に、新しい実験IDと保存先を作成し、seedのみ10〜19へ変更した。[追加実験の保存設定](../results/shared_five_models_full_20261010T041019864060Z/experiment_config.json)を出典とする。5モデル・10タスク・5条件・最大3修正round・temperature 0.7・1,024 tokens・600秒timeout・逐次実行とする。途中結果は暫定とし、API障害や未検証の結果から結論を確定しない。

共通3モデルには前回のseed 0〜9に加えて新しいseed 10〜19を収集する。追加2モデルは今回の10 seedのみであり、共通3モデルの20 seedと同じ標本数として扱わない。モデル・条件・タスク・seed・実験IDを保持し、共有round 0や同一seedの5条件を独立標本として数えない。seed変更だけで完全な独立性を保証せず、実験時点や保存されたモデルdigest・prompt・評価環境の差も確認する。まず各実験を別集計し、合算と統計的比較は完了・検証後に対象をそろえて行う。60分ごとの自動更新では、3モデル本実験の確定結果表と5モデル追加実験の進捗を別節で表示し、同じ表で比較しない。

<!-- auto:additional-results:start -->
### 5モデル追加実験の記録状況

集計時点：2026-10-16 00:00:06 JST。状態：検証済み（主分析への採否は別途判断）。

| 項目 | 状況 |
| --- | --- |
| 実験ID | `shared_five_models_full_20261010T041019864060Z` |
| 保存先 | `results/shared_five_models_full_20261010T041019864060Z/` |
| 予定件数 | 2,500件 |
| 現在の記録件数 | 2,500件 |
| 未記録件数 | 0件（全件照合済み） |
| 重複・予定外記録 | 0件・0件（集計時点の照合） |
| API障害・timeoutを明示する記録 | 0件（途中roundを含む検証済み） |
| API障害または未分類エラーの保守的な確認対象 | 0件 |
| sanity check・自動検証 | 成功 |


全件記録と検証は完了した。元実験の内訳として保持し、処理差を明記した固定時点の統合集計とは区別する。

| モデル | 条件 | 件数 | L2成功 | L3成功 |
| --- | --- | ---: | ---: | ---: |
| ollama:qwen3.5:4b | baseline | 100 | 20 | 20 |
| ollama:qwen3.5:4b | self_refine | 100 | 34 | 34 |
| ollama:qwen3.5:4b | execution_feedback | 100 | 53 | 53 |
| ollama:qwen3.5:4b | self_debugging | 100 | 61 | 61 |
| ollama:qwen3.5:4b | preventive_spec | 100 | 14 | 14 |
| ollama:gemma4:e4b-it-qat | baseline | 100 | 68 | 68 |
| ollama:gemma4:e4b-it-qat | self_refine | 100 | 85 | 85 |
| ollama:gemma4:e4b-it-qat | execution_feedback | 100 | 96 | 96 |
| ollama:gemma4:e4b-it-qat | self_debugging | 100 | 88 | 88 |
| ollama:gemma4:e4b-it-qat | preventive_spec | 100 | 31 | 31 |
| ollama:qwen3.5:9b | baseline | 100 | 57 | 57 |
| ollama:qwen3.5:9b | self_refine | 100 | 71 | 71 |
| ollama:qwen3.5:9b | execution_feedback | 100 | 81 | 81 |
| ollama:qwen3.5:9b | self_debugging | 100 | 78 | 78 |
| ollama:qwen3.5:9b | preventive_spec | 100 | 33 | 33 |
| ollama:qwen2.5-coder:7b | baseline | 100 | 66 | 66 |
| ollama:qwen2.5-coder:7b | self_refine | 100 | 74 | 74 |
| ollama:qwen2.5-coder:7b | execution_feedback | 100 | 78 | 78 |
| ollama:qwen2.5-coder:7b | self_debugging | 100 | 77 | 77 |
| ollama:qwen2.5-coder:7b | preventive_spec | 100 | 66 | 66 |
| ollama:gemma3:4b | baseline | 100 | 1 | 1 |
| ollama:gemma3:4b | self_refine | 100 | 1 | 1 |
| ollama:gemma3:4b | execution_feedback | 100 | 1 | 1 |
| ollama:gemma3:4b | self_debugging | 100 | 1 | 1 |
| ollama:gemma3:4b | preventive_spec | 100 | 7 | 7 |

### 2モデル補完実験の記録状況

集計時点：2026-10-16 00:00:06 JST。状態：検証済み（主分析への採否は別途判断）。

| 項目 | 状況 |
| --- | --- |
| 実験ID | `shared_two_models_seed0_9_full_20261012T100658266051Z` |
| 保存先 | `results/shared_two_models_seed0_9_full_20261012T100658266051Z/` |
| 予定件数 | 1,000件 |
| 現在の記録件数 | 1,000件 |
| 未記録件数 | 0件（全件照合済み） |
| 重複・予定外記録 | 0件・0件（集計時点の照合） |
| API障害・timeoutを明示する記録 | 0件（途中roundを含む検証済み） |
| API障害または未分類エラーの保守的な確認対象 | 0件 |
| sanity check・自動検証 | 成功 |


全件記録と検証は完了した。元実験の内訳として保持し、処理差を明記した固定時点の統合集計とは区別する。

| モデル | 条件 | 件数 | L2成功 | L3成功 |
| --- | --- | ---: | ---: | ---: |
| ollama:qwen2.5-coder:7b | baseline | 100 | 66 | 66 |
| ollama:qwen2.5-coder:7b | self_refine | 100 | 74 | 74 |
| ollama:qwen2.5-coder:7b | execution_feedback | 100 | 80 | 80 |
| ollama:qwen2.5-coder:7b | self_debugging | 100 | 78 | 78 |
| ollama:qwen2.5-coder:7b | preventive_spec | 100 | 63 | 63 |
| ollama:gemma3:4b | baseline | 100 | 1 | 1 |
| ollama:gemma3:4b | self_refine | 100 | 1 | 1 |
| ollama:gemma3:4b | execution_feedback | 100 | 1 | 1 |
| ollama:gemma3:4b | self_debugging | 100 | 1 | 1 |
| ollama:gemma3:4b | preventive_spec | 100 | 11 | 11 |
<!-- auto:additional-results:end -->

追加実験のqwen3.5:4b／T3a_DJ_constant／seed 19のbaselineとself_refineは、`simulator` と定義した変数を `sim` と参照したため、コード実行段階で停止した。指定された2記録の最終結果と該当する全5 round評価を `exec / interface_mismatch / NameError` に再分類し、メッセージを `name 'sim' is not defined` に統一した。self_refineはbaselineと同じ初回生成から派生し、3回修正後も同じ変数名不一致が残ったケースである。API接続障害・timeoutには含めず、L0・L1・L2・structure_match・L3は再評価せず保持した。再分類前のraw.jsonlをバックアップし、[変更・検証記録](additional_nameerror_reclassification.json)に保存先とSHA-256を記録した。2026-10-11 18:09 JSTの再集計では、途中roundを含む保守的な確認対象は再分類前の5件から3件となった。その後、残る3記録も次段落のとおり再分類した。最新件数は上の自動更新表を参照する。

追加の再分類では、T3a_DJ_constant／seed 19のexecution_feedbackのround 0とself_debuggingのround 0・1に残っていた同じNameErrorを `exec / interface_mismatch` に統一した。execution_feedbackのround 2・3と最終結果の `get_counts('')`、T3b_DJ_balanced／seed 16のself_debuggingのround 2・3と最終結果の `get_counts('0')` は、存在しない実験名によるQiskitErrorとして同じ分類に変更した。T3a_DJ_constantのself_debuggingの最終結果は古典ビット未確保による `build / build_error / CircuitError` を維持した。再分類前のraw.jsonlを別途バックアップし、生成コード・評価値・timeout_flagは変更せず、再実行・再評価も行っていない。[追加の変更・検証記録](additional_remaining_reclassification.json)にバックアップ、ハッシュ、更新一覧、検証・CSVの出典を保存した。

2026-10-11 18:16 JSTの保存済み1,404件では、最終結果・round履歴ともunknown_errorは0件、API障害・timeoutの確認対象も0件だった。保存設定に基づくsanity checkを実施し、重複・予定外記録・共有round 0の不一致は0件、その他の記録整合性エラーもなかった。ただし収集中のため、未記録1,096件と条件未完備1組により全件sanity checkは不合格であり、実験完了・自動検証成功とは扱わない。通常の分析CSVは1,404件から再生成し、介入カタログCSVは5条件がそろった1,400件のみの暫定集計とした。未完備の4記録はカタログから除外し、失敗や救出0件として扱わない。集計後の進捗は上の自動更新表を参照する。

### seed 0〜19の補完・統合計画（2026年10月12日）

ユーザー指示により、qwen2.5-coder:7b・gemma3:4bのseed 0〜9を1,000件追加する。実験IDは `shared_two_models_seed0_9_full_20261012T100658266051Z`、[保存設定](../results/shared_two_models_seed0_9_full_20261012T100658266051Z/experiment_config.json)を基準とする。完了・検証後は既存1,500件と2,500件を合わせ、5モデル各1,000件、計5,000件の統合集計を別保存先に作成する。

追加5モデルの介入カタログは全2,500件から再生成し、分母がbaseline L2失敗288件と一致した。旧固定資料の分母137件は途中集計として保持し、最新結果の分析には使わない。旧3モデルと追加実験のエラー分類変更は診断文にも影響するため、統合値は混合手順の記述的結果として扱い、出典別の内訳を残す。[確認結果と統合方針](seed0_19_integration.md)を参照する。補完実験が未完了・未検証の間は5,000件の結果を確定しない。

## 5 考察

簡易実験では、qwen3.5:4bのbaseline失敗例に対して実行結果フィードバックと自己デバッグによる救出が観測された。これは、初回生成で失敗したコードでも修正によって期待出力へ到達し得ることを示す。一方、初期成功例では修正自体が行われないため、条件別の成功率だけでは修正手法の能力を比較できない。baseline失敗例を対象とした救出率を併記する必要がある。

生成前の注意事項追加では成功率の低下が観測された。原因の検討では、注意事項の長さ、出力コードの変化、import・インターフェース・回路ロジックの失敗を分けて確認する。今回の観測だけから、いずれかが原因であるとは断定しない。

検証済み3モデル本実験の考察では、モデル・タスク・seedを対応付けた成功率差と救出・退行を調べ、必要な生成時間やトークン数も併せて比較する。修正回数が増えることで品質が改善した場合でも、追加コストとの関係を示す。

### 失敗類型別の介入カタログ

対象は検証済み主分析 `shared_three_models_full_20261008T103231611899Z` の保存済み1,500件である。3モデル × 10タスク × 10 seedのbaseline 300件のうち、L2失敗161件を対象とした。分類には同じ `model_spec, task_id, seed` のbaseline recordに保存された `error_category` をそのまま用い、介入後の失敗原因で分類し直さない。救出はbaseline L2失敗から介入後の最終L2成功への変化であり、途中roundの成功やL3成功とは区別する。

条件全体の成功率には初期成功例が含まれ、モデルごとの初期失敗の構成も異なる。baseline失敗類型ごとに同じ失敗例を分母とすることで、どの種類の失敗に介入が有効だったかを確認できる。下表は救出件数／baseline失敗件数（救出率）である。4条件は同じbaselineと対応付けた比較であり、4倍の独立標本としては扱わない。

| baseline失敗類型 | baseline失敗件数 | self_refine（修正） | execution_feedback（修正） | self_debugging（修正） | 修正型内の観測最多 |
| --- | ---: | ---: | ---: | ---: | --- |
| import_error | 48 | 11/48（22.9%） | 24/48（50.0%） | 29/48（60.4%） | self_debugging |
| syntax | 33 | 12/33（36.4%） | 12/33（36.4%） | 10/33（30.3%） | self_refine・execution_feedback（同率） |
| wrong_output | 31 | 14/31（45.2%） | 14/31（45.2%） | 17/31（54.8%） | self_debugging |
| build_error | 28 | 4/28（14.3%） | 16/28（57.1%） | 17/28（60.7%） | self_debugging |
| interface_mismatch | 21 | 8/21（38.1%） | 14/21（66.7%） | 13/21（61.9%） | execution_feedback |

import_errorとbuild_errorでは、self_debuggingおよびexecution_feedbackがself_refineより多くの失敗を救出した。wrong_outputでもself_debuggingが観測最多だった。interface_mismatchではexecution_feedbackが最多だが、self_debuggingとの差は1件であり、手法の優越性を断定しない。syntaxは修正型3条件でも救出率30.3〜36.4%と比較的低く、最多の2条件でも21/33件が未救出だった。self_refineによるbuild_errorの救出も4/28件と低かった。これらは現在のプロンプト・モデル・タスク集合・最大3修正回数での観測であり、失敗原因一般に対する手法の限界と断定しない。

生成前介入は次の別表に示す。preventive_specはbaselineのコードを修正せず、注意事項を付けた異なるプロンプトから1回生成する。その救出率は対応するbaseline失敗例での出力改善を表し、修正型条件の修正能力と同じ意味では解釈しない。

| baseline失敗類型 | preventive_spec（生成前）：救出件数／失敗件数（救出率） |
| --- | ---: |
| import_error | 3/48（6.3%） |
| syntax | 2/33（6.1%） |
| wrong_output | 5/31（16.1%） |
| build_error | 4/28（14.3%） |
| interface_mismatch | 8/21（38.1%） |

preventive_specはinterface_mismatchで8件を救出したが、syntaxとimport_errorでは救出率が約6%だった。また、baseline L2成功139件のうち93件がpreventive_specでL2失敗へ退行した。失敗例の救出だけから生成前介入全体の有効性を判断しない。

モデル別・難度別の内訳にも注意する。import_error 48件はすべてqwen3.5:4bであり、この救出率を3モデル共通の効果と解釈しない。build_errorでは全体の観測最多がself_debuggingである一方、qwen3.5:4bではexecution_feedbackが11/18件、self_debuggingが9/18件だった。hardのsyntaxではself_refineとexecution_feedbackが各5/19件、self_debuggingが3/19件にとどまる。カテゴリ構成とモデル・難度の偏りを保った内訳を参照して解釈する。

少数例は参考値とする。`best_intervention_flag` は修正型3条件内の標本上の最多を示す文字列であり、統計的な最良手法を示す真偽値ではない。baseline失敗分母10件未満は「参考」、10件以上で救出最多なら「観測最多」（同率の場合は「観測最多（同率）」）、他は「最多以外」、全修正型で救出0件なら「救出なし」とする。10件は表示上の基準であり、有意差や十分な精度を保証しない。preventive_specは「参考（生成前介入）」として修正型の最多判定から分ける。全体の失敗類型は21〜48件だが、モデル別・難度別では1〜8件の層もある。例えばeasyのwrong_outputは1件、mediumのinterface_mismatchは2件であり、救出率が100%でも有効性を断定しない。baseline失敗が観測されない層はCSV行を作らず、救出率0%とは扱わない。

追加CSVの列は以下の意味で用いる。`baseline_failure_count` は対応するbaseline L2失敗数、`rescued_count` はそのうち最終L2成功となった数、`rescue_rate` は両者の比（0〜1）である。`regression_count` はbaseline L2成功から介入後L2失敗への退行数であり、失敗類型行では定義上0になる。退行を消失させないため、baseline成功類型 `ok` を参照行として残し、失敗数・救出数は0、救出率は空欄、flagは「対象外（baseline L2成功）」とする。`ok` は失敗類型の順位付けに含めない。`degradation_count` は同じ修正条件内で最終roundの段階点が初期roundより低下した記録数（L0失敗=0、L1失敗=1、L2失敗=2、構造不一致=3、L3成功=4）で、preventive_specには適用せず0とする。`timeout_count` は最終結果または途中roundにtimeoutフラグ／api_timeoutがある記録数で、同じ記録内の複数timeoutは1件と数える。悪化・timeoutはその行のbaseline分類に対応する介入記録を数え、救出・退行とは別に判定する。

追加CSVは[類型別](../results/shared_three_models_full_20261008T103231611899Z/intervention_catalog_by_error.csv)、[類型×モデル別](../results/shared_three_models_full_20261008T103231611899Z/intervention_catalog_by_error_model.csv)、[類型×難度別](../results/shared_three_models_full_20261008T103231611899Z/intervention_catalog_by_error_difficulty.csv)である。各CSVの集計粒度は異なるため、3ファイルを足し合わせない。全体集計の救出237件（self_refine 49、execution_feedback 80、self_debugging 86、preventive_spec 22）、退行93件、修正過程の悪化41件、timeout 0件は既存集計と一致した。救出237件は4条件の合計であり、ユニークなbaseline失敗数ではない。保存設定に基づくsanity checkを再確認し、欠落・重複・予定外記録・共有初期評価の不一致は0件だった。

再現用の[集計スクリプト](../scripts/analyze_intervention_catalog.py)は追加3CSVだけを出力し、不完全な対応組や重複があれば集計を停止する。生成・コード実行・再評価は行わず、raw.jsonlと既存CSVは変更しない。入力SHA-256は `3fcf63e17659b8179d965be18d3583acf6adbab662466783c3dcecefb77dd515` である。再集計は次のコマンドで行う。

```bash
.venv/bin/python -m scripts.analyze_intervention_catalog results/shared_three_models_full_20261008T103231611899Z/raw.jsonl
```

## 6 限界

簡易実験は各モデル・条件につき4件であり、難タスクを含まない。2回の実行は同じseed集合を使用しているため、反復結果を独立標本として扱った統計的な有意差は主張しない。本実験でも同じ初期コードを共有する条件の記録は独立ではない。

構造評価はタスクに定義されたoracleの範囲に限られ、すべてのゲート種・深さ・測定要件を完全に検証するものではない。bit_order_errorは分布のビット反転比較に基づく判定である。

分布評価は有限shotsを用い、現行評価器ではシミュレータseedを固定していない。モデルへのseed指定だけでは、再評価まで含めた完全な再現性は保証されない。

生成長は1回1,024 tokensに制限される。API障害や生成長の上限による影響をモデルの量子回路ロジック能力と混同しない。共有サーバ上の経過時間は他の負荷の影響を受け得る。

条件別のトークン数と経過時間には共有初期生成の値が含まれるため、全条件の値を単純に合計すると初期生成を重複計上する。実際のAPI総使用量とは分けて解釈する。pricing未設定の金銭コストは未算出であり、0円とは扱わない。

## 7 今後の分析と追加実験完了後の確認

- 5モデル追加実験の全2,500レコードについて、整合性確認・分類確認・sanity check・自動検証・API障害確認を完了し、主分析への採否を判断する。3モデル本実験の全1,500件は確認済みである。
- モデル × 条件のL2・L3成功率、およびタスク別・難度別の件数と成功率。
- baseline失敗類型別の救出率、baseline退行、修正過程の悪化。
- 成功に至ったround、生成時間、トークン数、コード行数、ゲート数、回路深さ。
- API障害の元結果と、実施した場合の対応条件をそろえた追試結果。
- 対応付きデータと標本数に適した不確実性の評価、および代表的な成功・失敗例の分析。

## 8 再現用設定と根拠ファイル

実験方法は[標準5モデル追加実験設定](../configs/shared_five_models_full.json)、[簡易実験設定](../configs/shared_three_models_quick.json)、[実行処理](../scripts/run_experiment.py)、[修正処理](../harness/runner.py)、[評価器](../harness/evaluator.py)、[APIクライアント](../harness/llm_clients.py)に対応する。旧モデル名が残る[新ハーネス仕様](new_harness_spec.md)よりも、今回のモデル構成については実験ごとの保存設定を優先する。

- 簡易実験1：[保存設定](../results/shared_three_models_quick_20261007T123904531170Z/experiment_config.json)、[条件別集計](../results/shared_three_models_quick_20261007T123904531170Z/summary_by_condition.csv)、[救出率](../results/shared_three_models_quick_20261007T123904531170Z/rescue_rates_by_error.csv)、[baseline退行](../results/shared_three_models_quick_20261007T123904531170Z/baseline_regressions.csv)、[sanity report](../results/shared_three_models_quick_20261007T123904531170Z/sanity_report.json)、[自動検証](../results/shared_three_models_quick_20261007T123904531170Z/automation_report.json)、[manifest](../results/shared_three_models_quick_20261007T123904531170Z/manifest.json)。
- 簡易実験2：[保存設定](../results/shared_three_models_quick_20261007T123904532290Z/experiment_config.json)、[条件別集計](../results/shared_three_models_quick_20261007T123904532290Z/summary_by_condition.csv)、[救出率](../results/shared_three_models_quick_20261007T123904532290Z/rescue_rates_by_error.csv)、[baseline退行](../results/shared_three_models_quick_20261007T123904532290Z/baseline_regressions.csv)、[sanity report](../results/shared_three_models_quick_20261007T123904532290Z/sanity_report.json)、[自動検証](../results/shared_three_models_quick_20261007T123904532290Z/automation_report.json)、[manifest](../results/shared_three_models_quick_20261007T123904532290Z/manifest.json)。
- 旧本実験：[保存設定](../results/shared_three_models_full_20261007T145103982885Z/experiment_config.json)、[manifest](../results/shared_three_models_full_20261007T145103982885Z/manifest.json)。1,500件を記録したが、接続障害738件とround履歴を含む未分類エラー8記録があり、保存済み検証で停止した。主分析から除外し、接続障害の参考記録として元結果を保持する。
- 検証済み3モデル本実験（主分析）：[保存設定](../results/shared_three_models_full_20261008T103231611899Z/experiment_config.json)、[manifest](../results/shared_three_models_full_20261008T103231611899Z/manifest.json)。接続回復対策を適用し、同じ3モデル・10タスク・10 seed・5条件で全1,500件を記録済み。今回の再分類・再検証でsanity checkと自動検証が成功した。本文の3モデル本実験結果表はこの検証済み実験のみを対象とし、5モデル途中結果は混ぜない。途中集計と旧本実験は[スナップショット](experiment_report_snapshot.json)を参照する。未完了・未検証の結果は暫定とし、元のraw.jsonlは公開対象に含めない。

- 5モデル追加実験（全件検証済み）：実験ID `shared_five_models_full_20261010T041019864060Z`、保存先 `results/shared_five_models_full_20261010T041019864060Z/`。[保存設定](../results/shared_five_models_full_20261010T041019864060Z/experiment_config.json)、[manifest](../results/shared_five_models_full_20261010T041019864060Z/manifest.json)。全2,500件、実際のseedは10〜19。出典別の検証済み結果と、処理差を明記した統合結果を分ける。raw.jsonlなどの生データは公開対象に含めない。

現在の追加実験を重ねて起動しない。別の新しい5モデル実験を開始する場合の標準設定（seed 0〜9）のコマンドは以下である。

```bash
.venv/bin/python -m scripts.automate_experiment --config configs/shared_five_models_full.json --new-run
```

実行済みの時刻付き実験を再開する場合は、対象ディレクトリの `experiment_config.json` を指定し、`--new-run` を付けない。実行中の同じ実験を重ねて開始しない。


## 発表資料の固定出典と到達水準分析（2026-10-13）

旧共有版の固定集計は2026-10-13 00:45:35 JST。[固定出典と詳細表](presentation_sources/20261013T_levels_verified/README.md)に基づき、[中間発表](midterm2026/paper.pdf)と[WiNF下書き](winf2026/paper.pdf)を当時更新した。3モデル1,500件と5モデル2,500件をそれぞれ再検証し、追加実験の介入カタログ3種類の分母が288件と全件に一致することを確認した。旧19件の途中値や分母137件の固定資料は歴史的出典として保持し、現行共有原稿の確定結果には用いない。この旧固定資料は補完実験を含めない。現行共有版は次節の検証済み統合5,000件を参照する。

L0〜L3の累積達成率に加え、未達／L0のみ／L1まで／L2まで／L3の排他的な内訳と、対応付きの5×5遷移を示した。主分析のR・F・DでL3に届かなかった部分改善は11・20・22件、追加分析では16・20・25件だった。部分改善は段階上昇の内数であり、L3救出と区別する。初期L3成功139件／212件は修正型条件ごとに無修正終了しており、全件達成率だけで修正能力を判断しない。Pは別プロンプトの独立生成として分ける。

構造検証は量子ビット数と測定操作を除いた回路命令数の範囲に限定される。全10タスクでは古典ビット数・測定数・測定の必須／禁止は未指定であり、ゲート種・深さ・最適性・全入力での正しさを完全には検証しない。タスク定義は両実験の実行時コミットと一致することを確認した。保存済み評価だけを集計し、生成コードや評価値は変更していない。

## seed 0〜19の検証済み統合集計

固定集計時点：2026-10-13 14:45:33 JST。[固定出典と詳細表](presentation_sources/20261013T_pooled_verified/README.md)を参照。

検証済み3モデル1,500件、5モデル追加2,500件、2モデル補完1,000件から各モデル1,000件、計5,000件を統合した。L2・L3成功は2,457件（49.14%）、失敗2,543件。欠落・重複・予定外記録0件、sanity・automation・介入カタログ検証成功。補完実験の未分類1件は生成コードのstatevector取得手順の誤用へ読み込み時に再分類し、生データと評価値は保持した。

初期未達582件を分母に、R・F・Dの救出は110・191・191件。Pは独立生成で救出85件、退行210件。schema 2.0と2.1の診断文処理差を含む混合手順の記述的結果であり、単一手順の介入効果や統計的有意差を示すものではない。元実験別の内訳と設定を保持する。

## モデル・難度・seed別の層別分析（2026-10-13）

[詳細レポートとCSV](analysis/model_difficulty_seed_20261013/README.md)に、統合5,000件と元3実験別の救出率・部分改善・段階低下を保存した。モデル別、難度別、モデル×難度、seedブロック、個別base seed、失敗類型など全11区分で、分割集計と出典別合計の一致を検証した。分母0の率は空欄とし、初期未達10件未満の層を参考値として明示する。

qwen3.5:4bではD 83/165件、F 74/165件、gemma4ではF 50/67件、D 43/67件を救出した。easy・mediumの全体ではD、hardではFの救出件数が観測最多だった。ただしモデル×難度では内訳が異なる。gemma4とqwen3.5:9bでは、seed 0〜9と10〜19でF・Dの救出数の大小も変わった。出典・実施時期・schemaによる診断文処理差が交絡するため、seedだけの効果や一般的な最適介入とは解釈しない。

初期未達582件に対し、FとDがともに救出した例は149件、Fのみ42件、Dのみ42件、どちらでも未達349件であった。最終救出数が同じでも対象例は異なる。次は片方だけで救出した例と、部分改善がL3へ届かなかった例を、baselineの失敗類型・タスクに沿って確認する。元の生データ・生成コード・評価値は保持し、新規生成や再評価は行っていない。

## Fのみ・Dのみ救出例の比較（2026-10-13）

[観測結果とコード確認メモ](analysis/feedback_debugging_discordant_20261013/findings.md)、[全表・修正履歴](analysis/feedback_debugging_discordant_20261013/README.md)に、Fのみ42件とDのみ42件を保存した。分母はbaselineのL3未達582件とし、共通救出149件・どちらも未達349件を含めて比較する。元recordと生成コードのhash、各roundの評価段階・失敗分類を追跡できる。

import_errorはFのみ8件・Dのみ18件（全救出55/271件・65/271件）、syntaxは9件・2件（25/68件・18/68件）。回路構築は各11件の片側救出で全救出57/106件ずつだった。importの差は主にqwen3.5:4b、構文の差はgemma4に現れた。Grover・QPE・IQFTはFのみ、BV・DJ constantはDのみの救出が多い。モデル・タスク・出典別の分母を確認し、一般的な介入選択ルールではなく使い分けの候補として扱う。

84例の修正履歴と、4例の保存コードを静的に確認した。初期エラーを直しても別のimport・結果取得失敗を追加した例があった。gemma4のQPE seed 16では、未使用古典ビット3個があるroundの保存分布1010000から、古典ビットを持たないF round 2の1010へ変わり、期待分布と一致した。出力不一致を量子論理の誤りだけに帰属させず、評価用測定追加と出力表現への感度を限界として記録する。生データと原判定は保持し、追加生成・再評価は行っていない。

## 改善と追加生成コストの比較（2026-10-13）

[観測結果](analysis/repair_costs_20261013/findings.md)、[詳細表と定義](analysis/repair_costs_20261013/README.md)に、修正round 1以降の時間・tokensをモデル・難度・出典別に保存した。初期成功418件の無修正終了を分け、共有初期生成を重複計上しない。生成要求のelapsed_secには再接続待機も含まれ、評価・解析の時間と金銭コストを表すものではない。

未救出例も含む追加tokens／救出はR 17,365.1、F 9,584.8、D 11,103.4。追加秒／救出は841.6、464.8、574.8だった。FとDはともに191件を救出し、Fの全修正tokensは約13.7%、要求時間は約19.1%少なかった。qwen3.5:4bではDの救出が9件多く、モデル別の成功数とコストの交換関係を保持する。未救出例へのtokensは全修正分のR 88.7%、F 82.0%、D 81.7%であり、部分改善の存在も踏まえて解釈する。

Pは独立生成1,000件の全コスト764,083 tokens・11.92時間として分け、293件の最終成功、85件の救出、210件の退行を併記した。B＋修正条件のワークフロー全体も別表に保存し、Pの全生成分を修正追加分と同一視しない。全実験の記録された生成roundは共有初期の重複3,000行を除いて6,517回、7,285,688 tokens・104.94時間。成功した接続回復を含む生成round 20回と再試行40回を時間の制約として記録する。出典・実施時期・診断文処理差のある記述的結果であり、一般的優劣は断定しない。

## 修正上限1・2・3回の観測済み履歴比較（2026-10-13）

[観測結果](analysis/repair_limits_20261013/findings.md)、[詳細表と定義](analysis/repair_limits_20261013/README.md)に、同じ最大3回修正の履歴を各上限で区切った結果を保存した。上限を変えた新しい実験ではなく、観測済みの途中経過の比較である。初期成功418件は無修正で保持し、上限別件数・コストを合計しない。

初期未達582件の累積救出はR 65→90→110件、F 119→166→191件、D 114→167→191件。3回目の追加救出はF 25/416件（直前まで未達の実施組を分母）、D 24/415件で、追加528,848 tokens・6.70時間と619,981 tokens・8.35時間だった。上限2回で停止するとFは3回までの救出の86.9%、Dは87.4%を保ち、修正tokensを28.9%、29.2%減らす計算になる一方、3回目の救出例は失われる。

qwen3.5:4bでは3回目にF・Dが各12件を救出し、gemma4ではF 7件・D 2件だった。モデル・難度・初期失敗類型・seedブロック・出典別の分母と追加コストを保持し、一般的な最適上限は確定しない。共有初期生成を除いた追加分と、初期生成を1回加えたworkflow全体を分け、上限3回の値を前段のコスト分析と照合した。新規生成・再評価は行っていない。

## 3回目の救出例と継続条件（2026-10-13）

[観測結果](analysis/third_round_20261013/findings.md)、[詳細表・履歴](analysis/third_round_20261013/README.md)に、F 25件・D 24件の3回目救出を保存した。共通3組を除くと46初期組で、分母は2回目まで未達のF 416件・D 415件。全13区分と出典別集計は前段の上限3回の件数・コストに一致した。

直前類型ではFのimport・出力不一致から各9件、Dのimportから9件・回路構築失敗から8件を救出した。qwen3.5:4bは各12件、gemma4はF 7件・D 2件、gemma3は各0/198件であり、類型全体の率とモデル別の率を分ける。同じ分類がround 1・2で続いたら停止する候補ではF 18/25件・D 15/24件、初期から段階上昇した例だけ続ける候補ではF 19/25件・D 21/24件の救出を失う。単純な停止候補には救出を失う大きな交換関係がある。

モデル×直前類型を継続判断の探索候補とし、別seed・タスクでの検証前に運用方策を確定しない。49条件記録の196行の履歴と元record・コードhashを保持し、生データ・原判定は変更せず、新規生成・再評価は行っていない。

## 評価器の出力表現への感度確認（2026-10-14）

[確認結果](analysis/output_representation_20261014/README.md)に、確認用回路19例を保存した。正しいQPEへ未使用古典ビット3個を加えると、現行比較は1010000を1010と不一致として扱った。測定先から量子ビット順へ戻す比較候補では、正しい回路10例のうち現行で失敗する7例が成功し、誤った6例は不合格のまま、部分測定・上書き・途中測定の3例は対象外となった。

保存済み分布の2,880 round行中619行はタスク指定の量子ビット数と出力幅が異なった。共有初期の重複を含み、すべてが表現だけによる失敗とは判定できない。追加測定による余分な古典ビットの分離と、明示的測定の評価仕様の明文化を改善対象とする。比較候補は確認スクリプト内に限定し、現行評価器・保存判定・成功率は保持した。新たなLLM生成や保存生成コードの実行は行っていない。

## 測定先に基づく分布評価の採用（2026-10-14）

ユーザーの指示により、[新しい評価仕様](evaluator_readout.md)を本番評価器へ適用した。版はqubit_readout_v2。全量子ビットの一意な終端測定から量子ビット順の分布を復元し、未使用古典ビットを合算する。曖昧な測定はevaluate / interface_mismatchとして拒否し、ビット数・測定数・ゲート数などの構造条件は保持する。特定の測定先を要求する将来のタスクには、その配置の検証を別途追加する。

新規実験のmanifestへ評価器の版とソースhashを記録し、旧版で途中まで記録された実験への追加生成を防止する。旧実験の全件記録済みデータの検証・集計は許可する。検証済み5,000件、固定スナップショット、過去の成功率・救出数は新評価器で再評価しておらず、元の判定を保持する。今回の変更でLLM追加生成や既存生成コードの一括実行は行っていない。

## 5000件再評価前の評価方法点検（2026-10-14）

[点検結果](analysis/evaluation_methods_20261014/README.md)に、確認用回路38例と独立した期待値計算3例を保存した。全体位相のみが異なるQFT・逆QFT・Ansatzの6例を誤って落とす符号不具合を修正し、修正後は全例成功した。相対位相の異なる状態ベクトル3例と誤ったmock10例は不合格を維持した。シミュレータ・transpileのseedを42へ固定し、barrierの構造判定と未束縛パラメータなどの失敗分類も修正した。評価器の版はevaluation_policy_v3。

分布だけではBell・GHZの相対位相を識別できず、出力一致とゲート数だけではGroverなどのアルゴリズム手順を保証しない。L3は粗い構造条件を含む出力一致として解釈し、再評価では状態・構造の補助検査を別列に保存する方針を推奨する。閾値近辺のサンプリング不確かさも記録した。隔離実行と補助検査の設計を次の作業とし、今回5,000件の実行・再評価は行っていない。

## 文献と公式仕様に基づく追加監査（2026-10-14）

[追加監査](analysis/literature_reliability_20261014/README.md)に、指定6資料の原文アクセス、根拠箇所と18監査項目の対応を整理した。5資料の本文・仕様を確認し、Abreuらの本文は取得できず未確認とした。Qiskit 2.5.2・Aer 0.17.2の実装とも照合した。

82の制御検査、6 mutation、4プロセス検査、108 sampling組を記録した。主判定は6変異中4例、補助忠実度は6例すべてを検出したが、小さな選択集合の結果であり妥当性全体の証明ではない。部分resetの乱数分岐を主状態として比較する問題を修正し、主状態ベクトル評価はユニタリ回路へ限定した。版はevaluation_policy_v4。重複・破損JSONLの拒否と、評価器版・sampling方針の異なる結果の統合防止も追加した。

保存済み5,000件・1,000対応組・9,517 round行の初期共有と段階・成功位置は整合した。過去の生成コードは実行せず、元判定を保持した。本番再評価は隔離実行・専用checkpoint・補助オラクルが未検証のためNO-GO。通常のsubprocessテストを本番sandboxと同一視せず、旧feedback経路と主・補助指標を分ける。

## 文献原文と実装の対応の再点検（2026-10-14）

[再点検](analysis/literature_reliability_20261014/source_implementation_recheck/README.md)に、4論文PDFと指定仕様ミラーの取得日時・hash・確認ページを保存した。Abreuらの本文は今回も403で未確認とし、根拠から除外する。前報告の公開証跡の不足を補い、監査用コードと本番実装、独立した期待値と実行スタックの共有を区別した。

21項目を原文確認済み2、実装確認済み8、独立検証済み9、未確認2に整理した。忠実度の試行閾値0.9975は主距離0.05の厳密な換算と異なり、QFTの選択入力は列2位相を見逃すことを追加反例で確認した。対象80テスト成功。今回は本番コード・主判定・過去の評価値を変更せず、5,000件再評価は未開始のままNO-GOとする。


## 再評価NO-GO条件への対応と少数試験（2026-10-14）

[対応報告](analysis/reevaluation_readiness_20261014/README.md)にQFT/IQFTのcoherent入力補助、純粋状態距離0.05と忠実度の厳密換算、Linuxの二段階隔離・時間／CPU／メモリ制限、専用transactional checkpointと故障注入の検証を記録した。主判定evaluation_policy_v4を維持し、補助は別列へ保存する。全309テスト成功後、保存済み10記録・12 roundだけを実行し、実行基盤の失敗・欠落・重複keyは0。二つのcheckpointを再開して追加実行はともに0件だった。QFT/IQFTの生成済み正解2例は22入力補助でも成功した。

QPEで旧失敗の3 roundが主成功へ変わり、修正履歴の初成功はround 2から0になった。これは旧feedback経路の保存コードの再採点であり、新評価器を用いた介入の効果ではない。少数試験の結果を元の5,000件の成功率表や固定発表資料へ反映していない。元raw・設定のhashは不変で、LLM要求・追加生成・本番5,000件再評価・Git pushは行っていない。判定はCONDITIONAL GOとし、全件計画の検証・未確認タスクの資源適合・補助の適用範囲を確定してから本番実行を別途判断する。


## 再評価の準備条件の解消（2026-10-14）

[条件解消報告](analysis/reevaluation_completion_20261014/README.md)に、全5,000記録・9,517 roundの静的計画、残る6タスクの独立式による状態／変換補助、資源適合試験、基盤障害時の停止・再開拒否を記録した。旧空コードのhash欄欠落1件は原データを保持して計算hashと旧欄を別記し、構文エラー715 roundも評価対象として保持する。全324テスト成功後、全10タスク・5モデルの20記録・58 roundのみを隔離実行した。基盤障害・欠落・重複keyは0、両checkpointの再開で追加実行0。

主v4と別列補助を分離した保存コード再採点に対する準備判定はGOとする。QPE・Ansatzの固定状態一致と変換全体の相違、測定を含む補助適用外などの限界も記録した。未実行コード全ての資源適合を保証せず、基盤障害が出たら停止し誤答として算入しない。旧feedback経路・元5,000件の結果表・固定発表資料は維持し、追加LLM要求・本番5,000件再評価・Git pushは行っていない。


<!-- saved-reevaluation:reevaluation_full_20261014T141718Z:start -->
## 保存済み5,000件の本番再評価（reevaluation_full_20261014T141718Z）

状態：completed。計画5000記録・9517 round、保存済み9517 round。更新UTC：2026-10-14T19:21:51.612108+00:00。[実行状態](analysis/reevaluation_full_20261014T141718Z/run_status.json)と[出典・評価器manifest](analysis/reevaluation_full_20261014T141718Z/manifest.json)を別保存する。主v4・補助v2を分離し、旧raw・旧評価・固定発表結果を保持する。

採点完了5000記録・9517 round。基盤障害0件、欠落0 round。[比較・sanity](analysis/reevaluation_full_20261014T141718Z/final/summary.json)を参照する。完了記録の最終L3は旧2457→新2727。未分類主失敗12 round、共有初期判定不一致0組。旧feedbackで選ばれた保存コードの再採点であり、新しい介入実験ではない。LLM要求0、基盤障害時は停止。Git pushは行わない。
<!-- saved-reevaluation:reevaluation_full_20261014T141718Z:end -->


<!-- reevaluation-followup:20261015:start -->
## 2026-10-15 再評価後の影響監査と部分追試（別集計）

状態：completed。旧実験5,000記録、保存済み9,517 roundの全件再採点、停止経路の再構成、部分追試293/293ケースを分離した。追加生成647/773回（上限）。変更なし抽出：50共有初期グループ。[出典・各別表・限界](analysis/reevaluation_followup_20261015/README.md)を参照。保存prefixと新規suffixを組み合わせた結果を、新評価器で生成から実施した5,000件実験とは呼ばない。旧表と固定発表資料を保持する。共有初期・task/seed依存があるため独立二項試行や介入の因果効果を仮定しない。
<!-- reevaluation-followup:20261015:end -->
