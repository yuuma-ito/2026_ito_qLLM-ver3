# Qiskitコード生成におけるモデルと介入条件の比較実験レポート 下書き

本研究では、検証済み3モデル本実験を主分析とし、現在収集中の5モデル追加実験を別実験として、OllamaモデルによるQiskit量子回路コード生成を対象に、タスク難度と介入条件による生成品質の違いを調べる。構文・実行・出力・構造を分けて評価し、成功率だけでなく、失敗類型、修正による救出、退行、生成に要したトークン数と時間を比較する。

<!-- auto:status:start -->
簡易実験は2回完了した。3モデル本実験は全件記録と自動検証が完了した。モデル間・難度間の比較の考察は、検証済み結果に基づいて追記する。3モデル本実験を検証済みの主分析として採用し、5モデル追加実験は別実験ID・別保存先で収集する。追加実験の主分析への採否は完了・検証後に判断する。
<!-- auto:status:end -->

<!-- auto:capture:start -->
集計時点：2026-10-10 15:18:09 JST。数値は最終更新時点の値であり、60分ごと（毎時0分）に自動更新する。[集計スナップショット](experiment_report_snapshot.json)に同じ時点の件数と出典を保存する。
<!-- auto:capture:end -->

## 1 目的と比較の観点

量子回路コードの生成では、コードを実行できることと、期待する量子状態・測定分布を得られることを別に評価する必要がある。本実験では、初回生成の品質に加え、生成後の修正と生成前の注意事項の追加が、それぞれ評価結果をどの程度改善するかを検討する。

比較の観点は、モデルごとの生成品質、タスク難度による失敗の違い、介入条件によるbaseline失敗例の救出、介入によって成功例が失敗へ変わる退行、および品質と生成コストの関係である。APIヒントのablationおよび旧実験のH0〜H3・exp4は今回の対象に含めない。

## 2 実験方法

### 2.1 モデルと実行環境

検証済み主分析の対象は `qwen3.5:4b`、`gemma4:e4b-it-qat`、`qwen3.5:9b` の3モデルである。現在、`qwen2.5-coder:7b` と `gemma3:4b` を加えた5モデル追加実験を別実験ID・別保存先で実行している。実験設定ではモデル名に `ollama:` を付けて記録する。モデルの同定にはタグに加え、保存されたサーバ情報のdigestと量子化情報を用いる。タグの数値だけをモデルの正確な総パラメータ数とはみなさない。

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

旧2モデルがサーバに追加されたとの報告は、中間発表との比較を再検討する際に利用できる。ただし、前回の本実験は保存設定どおり3モデル・1,500件で完了し、旧2モデルを含む5モデルの追加実験を別記録として実行している。

追加実験として、旧2モデルを含む5モデル比較を別実験IDで実行している。対象は `qwen2.5-coder:7b`、`gemma3:4b`、`qwen3.5:4b`、`gemma4:e4b-it-qat`、`qwen3.5:9b` である。標準設定 `configs/shared_five_models_full.json` は10タスク・seed 0〜9・5条件で合計2,500件を予定する。ただし、現在実行中の保存設定ではseedを10〜19へ変更しており、実際の収集条件はこの保存設定に従う。現時点では収集中・未検証であるため、3モデル本実験とは分けて扱う。動作確認用の設定は `configs/shared_five_models_quick.json`（100件）である。旧2モデルの中間発表時の結果と比較する際は、ハーネスや条件の違いを明記する。

### 2.2 タスクと試行数

本実験では以下の10タスクを使用する。難度区分はハーネスのタスク分類に従う。

| 難度 | タスク |
| --- | --- |
| easy | T1 Bell、T2 GHZ |
| medium | T3a Deutsch–Jozsa constant、T3b Deutsch–Jozsa balanced、T4 Bernstein–Vazirani 011、T5 Grover 11 |
| hard | T6 QFT 001、T7 IQFT 001、T8 QPE 001、T9 Ansatz 001 |

検証済み3モデル本実験は、3モデル × 10タスク × 10 seed（0〜9）× 5条件 = 1,500レコードをすべて記録済みである。現在実行中の追加実験は、5モデル × 10タスク × 10 seed（10〜19）× 5条件 = 2,500レコードを予定する。標準5モデル設定のseed 0〜9と、実行中の保存設定のseed 10〜19を区別する。1レコードは1つのモデル・タスク・seed・条件の最終評価と修正履歴に対応する。修正roundを別のレコードとして数えない。

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
## 4 3モデル本実験の検証済み結果

実験ID：`shared_three_models_full_20261008T103231611899Z`。保存先：`results/shared_three_models_full_20261008T103231611899Z/`。

2026-10-10 15:18:09（日本時間）時点で、予定1,500件のうち1,500件（100.0%）を記録した。残りは0件である。L2成功は839件、L2失敗は661件、API障害を含む記録は0件であった。重複は0件、予定外記録は0件であった。

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

集計時点：2026-10-10 15:18:09 JST。状態：収集中または未検証・暫定。

| 項目 | 状況 |
| --- | --- |
| 実験ID | `shared_five_models_full_20261010T041019864060Z` |
| 保存先 | `results/shared_five_models_full_20261010T041019864060Z/` |
| 予定件数 | 2,500件 |
| 現在の記録件数 | 153件 |
| 未記録件数 | 2,347件（完了後の欠落判定は未確定） |
| 重複・予定外記録 | 0件・0件（集計時点の照合） |
| API障害・timeoutを明示する記録 | 0件（途中roundを含む暫定確認） |
| API障害または未分類エラーの保守的な確認対象 | 4件 |
| sanity check・自動検証 | 未完了・未検証 |

未分類エラーを含む保守的な確認対象は、API障害が確定した件数とは異なる。分類確認と最終検証を完了するまでAPI障害0件という最終結論は置かない。

L2成功率などの最終結果は未確定であり、3モデル本実験の結果表には混ぜない。主分析に含めるかどうかは、全件の収集・分類確認・sanity check・自動検証が完了した後に判断する。
<!-- auto:additional-results:end -->

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

- 5モデル追加実験（収集中・未検証）：実験ID `shared_five_models_full_20261010T041019864060Z`、保存先 `results/shared_five_models_full_20261010T041019864060Z/`。[保存設定](../results/shared_five_models_full_20261010T041019864060Z/experiment_config.json)、[manifest](../results/shared_five_models_full_20261010T041019864060Z/manifest.json)。予定2,500件、実際のseedは10〜19。進捗と確認状況は独立した進捗節を参照し、完了・検証後に主分析への採否を判断する。raw.jsonlなどの生データは公開対象に含めない。

現在の追加実験を重ねて起動しない。別の新しい5モデル実験を開始する場合の標準設定（seed 0〜9）のコマンドは以下である。

```bash
.venv/bin/python -m scripts.automate_experiment --config configs/shared_five_models_full.json --new-run
```

実行済みの時刻付き実験を再開する場合は、対象ディレクトリの `experiment_config.json` を指定し、`--new-run` を付けない。実行中の同じ実験を重ねて開始しない。
