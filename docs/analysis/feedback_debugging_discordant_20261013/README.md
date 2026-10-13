# 実行結果提示と自己デバッグの救出例比較

baselineのL3未達582件を対応付きで比較した。共通救出149件、Fのみ42件、Dのみ42件、どちらも未達349件。片方だけで救出した例を失敗類型・タスク・モデル・出典別に整理し、保存済みround履歴の変化を確認する。

F＝execution_feedback（実行結果提示）、D＝self_debugging（説明・原因分析・修正）。両者は同じ初期コード・初期評価を共有する。全体の救出率の分母は初期未達全件であり、選び出した片方だけの成功例ではない。表の各率も同じ行の初期未達件数を分母とする。

## baseline失敗類型別

| 失敗類型 | 初期未達 | 共通救出 | Fのみ | Dのみ | どちらも未達 | F救出率 | D救出率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| build_error | 106 | 46 | 11 | 11 | 38 | 53.8% | 53.8% |
| import_error | 271 | 47 | 8 | 18 | 198 | 20.3% | 24.0% |
| interface_mismatch | 32 | 11 | 3 | 2 | 16 | 43.8% | 40.6% |
| qubit_count_mismatch | 3 | 0 | 0 | 0 | 3 | 0.0% | 0.0% |
| syntax | 68 | 16 | 9 | 2 | 41 | 36.8% | 26.5% |
| wrong_output | 102 | 29 | 11 | 9 | 53 | 39.2% | 37.3% |

## タスク別

| タスク | 初期未達 | 共通救出 | Fのみ | Dのみ | どちらも未達 | F救出率 | D救出率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| T1_Bell | 37 | 10 | 1 | 4 | 22 | 29.7% | 37.8% |
| T2_GHZ | 37 | 13 | 1 | 2 | 21 | 37.8% | 40.5% |
| T3a_DJ_constant | 56 | 16 | 2 | 8 | 30 | 32.1% | 42.9% |
| T3b_DJ_balanced | 55 | 17 | 6 | 4 | 28 | 41.8% | 38.2% |
| T4_BV_011 | 64 | 16 | 2 | 9 | 37 | 28.1% | 39.1% |
| T5_Grover_11 | 73 | 7 | 11 | 6 | 49 | 24.7% | 17.8% |
| T6_QFT_001 | 67 | 31 | 2 | 4 | 30 | 49.3% | 52.2% |
| T7_IQFT_001 | 50 | 10 | 6 | 2 | 32 | 32.0% | 24.0% |
| T8_QPE_001 | 95 | 6 | 8 | 2 | 79 | 14.7% | 8.4% |
| T9_Ansatz_001 | 48 | 23 | 3 | 1 | 21 | 54.2% | 50.0% |

## モデル別

| モデル | 初期未達 | 共通救出 | Fのみ | Dのみ | どちらも未達 | F救出率 | D救出率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| gemma3:4b | 198 | 0 | 0 | 0 | 198 | 0.0% | 0.0% |
| gemma4:e4b-it-qat | 67 | 38 | 12 | 5 | 12 | 74.6% | 64.2% |
| qwen2.5-coder:7b | 68 | 21 | 5 | 2 | 40 | 38.2% | 33.8% |
| qwen3.5:4b | 165 | 59 | 15 | 24 | 67 | 44.8% | 50.3% |
| qwen3.5:9b | 84 | 31 | 10 | 11 | 32 | 48.8% | 50.0% |

## モデルと失敗類型の組合せ

| モデル | 失敗類型 | 初期未達 | 共通救出 | Fのみ | Dのみ | どちらも未達 | F救出率 | D救出率 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| gemma3:4b | build_error | 13 | 0 | 0 | 0 | 13 | 0.0% | 0.0% |
| gemma3:4b | import_error | 157 | 0 | 0 | 0 | 157 | 0.0% | 0.0% |
| gemma3:4b | interface_mismatch | 10 | 0 | 0 | 0 | 10 | 0.0% | 0.0% |
| gemma3:4b | qubit_count_mismatch | 3 | 0 | 0 | 0 | 3 | 0.0% | 0.0% |
| gemma3:4b | syntax | 2 | 0 | 0 | 0 | 2 | 0.0% | 0.0% |
| gemma3:4b | wrong_output | 13 | 0 | 0 | 0 | 13 | 0.0% | 0.0% |
| gemma4:e4b-it-qat | build_error | 13 | 10 | 1 | 1 | 1 | 84.6% | 84.6% |
| gemma4:e4b-it-qat | import_error | 4 | 3 | 1 | 0 | 0 | 100.0% | 75.0% |
| gemma4:e4b-it-qat | interface_mismatch | 11 | 9 | 0 | 1 | 1 | 81.8% | 90.9% |
| gemma4:e4b-it-qat | syntax | 17 | 11 | 5 | 0 | 1 | 94.1% | 64.7% |
| gemma4:e4b-it-qat | wrong_output | 22 | 5 | 5 | 3 | 9 | 45.5% | 36.4% |
| qwen2.5-coder:7b | build_error | 21 | 10 | 1 | 1 | 9 | 52.4% | 52.4% |
| qwen2.5-coder:7b | import_error | 19 | 5 | 1 | 1 | 12 | 31.6% | 31.6% |
| qwen2.5-coder:7b | wrong_output | 28 | 6 | 3 | 0 | 19 | 32.1% | 21.4% |
| qwen3.5:4b | build_error | 38 | 13 | 6 | 5 | 14 | 50.0% | 47.4% |
| qwen3.5:4b | import_error | 91 | 39 | 6 | 17 | 29 | 49.5% | 61.5% |
| qwen3.5:4b | interface_mismatch | 9 | 2 | 1 | 1 | 5 | 33.3% | 33.3% |
| qwen3.5:4b | syntax | 17 | 2 | 1 | 0 | 14 | 17.6% | 11.8% |
| qwen3.5:4b | wrong_output | 10 | 3 | 1 | 1 | 5 | 40.0% | 40.0% |
| qwen3.5:9b | build_error | 21 | 13 | 3 | 4 | 1 | 76.2% | 81.0% |
| qwen3.5:9b | interface_mismatch | 2 | 0 | 2 | 0 | 0 | 100.0% | 0.0% |
| qwen3.5:9b | syntax | 32 | 3 | 3 | 2 | 24 | 18.8% | 15.6% |
| qwen3.5:9b | wrong_output | 29 | 15 | 2 | 5 | 7 | 58.6% | 69.0% |

## 出典別

| 実験ID | 初期未達 | 共通救出 | Fのみ | Dのみ | どちらも未達 | F救出率 | D救出率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| shared_five_models_full_20261010T041019864060Z | 288 | 75 | 22 | 18 | 173 | 33.7% | 32.3% |
| shared_three_models_full_20261008T103231611899Z | 161 | 63 | 17 | 23 | 58 | 49.7% | 53.4% |
| shared_two_models_seed0_9_full_20261012T100658266051Z | 133 | 11 | 3 | 1 | 118 | 10.5% | 9.0% |

モデル×タスク、元実験別の失敗類型・モデル・タスクの全表はcomparisons.csvを参照。初期失敗がない層は行を作らず、初期未達10件未満はsmall_denominatorで参考値として明示する。片方だけの例の比率を、全体の救出率と混同しない。

## 保存済み履歴の確認例

各条件・baseline失敗類型からcase_id順の先頭例を示す。頻度による代表例や典型例の選定ではなく、履歴を追跡するための例示である。okは利用可能な構造要件を含むL3達成。分類の変化は記録された評価結果であり、生成コードを再実行したものではない。

| case ID | 救出条件 | モデル／タスク／base seed | baseline類型 | Fのround履歴 | Dのround履歴 |
| --- | --- | --- | --- | --- | --- |
| 020ea198c9d86365 | D | qwen3.5:9b／T4_BV_011／6 | build_error | 0:build_error -> 1:wrong_output -> 2:wrong_output -> 3:syntax | 0:build_error -> 1:syntax -> 2:syntax -> 3:ok |
| 032e66c38b941e42 | D | gemma4:e4b-it-qat／T7_IQFT_001／2 | wrong_output | 0:wrong_output -> 1:wrong_output -> 2:wrong_output -> 3:wrong_output | 0:wrong_output -> 1:build_error -> 2:ok |
| 042375a50346c20c | F | qwen3.5:4b／T3b_DJ_balanced／19 | build_error | 0:build_error -> 1:ok | 0:build_error -> 1:import_error -> 2:import_error -> 3:interface_mismatch |
| 05bf2d436b25b19d | D | qwen3.5:4b／T3b_DJ_balanced／7 | import_error | 0:import_error -> 1:build_error -> 2:import_error -> 3:import_error | 0:import_error -> 1:interface_mismatch -> 2:import_error -> 3:ok |
| 080c10ce4853fb80 | F | qwen3.5:4b／T3b_DJ_balanced／10 | import_error | 0:import_error -> 1:syntax -> 2:import_error -> 3:ok | 0:import_error -> 1:import_error -> 2:import_error -> 3:import_error |
| 11cd0a9bcc8b5388 | F | qwen3.5:9b／T7_IQFT_001／1 | interface_mismatch | 0:interface_mismatch -> 1:ok | 0:interface_mismatch -> 1:build_error -> 2:syntax -> 3:syntax |
| 1a8625f0c66ec4df | F | qwen3.5:9b／T5_Grover_11／19 | syntax | 0:syntax -> 1:ok | 0:syntax -> 1:syntax -> 2:syntax -> 3:syntax |
| 2cf271244f2ea0cd | F | gemma4:e4b-it-qat／T8_QPE_001／16 | wrong_output | 0:wrong_output -> 1:wrong_output -> 2:ok | 0:wrong_output -> 1:wrong_output -> 2:wrong_output -> 3:wrong_output |
| 445a5da9184e26b5 | D | qwen3.5:9b／T5_Grover_11／6 | syntax | 0:syntax -> 1:syntax -> 2:syntax -> 3:syntax | 0:syntax -> 1:syntax -> 2:ok |
| 76e58591ffa1c661 | D | gemma4:e4b-it-qat／T6_QFT_001／9 | interface_mismatch | 0:interface_mismatch -> 1:wrong_output -> 2:interface_mismatch -> 3:interface_mismatch | 0:interface_mismatch -> 1:wrong_output -> 2:ok |

履歴のerror_category列は各roundの失敗原因、level列は累積的な到達段階を示す。成功した条件がL3へ進む一方、もう一方が同じ類型を繰り返した例と、別の失敗類型へ移った例を区別できる。変更の具体的な原因や診断文の有効性を確定するには、別途コード・フィードバックの内容確認が必要となる。

## 解釈と介入の使い分け

片方だけの救出例は比較の候補であり、失敗類型から最適介入を決めるルールではない。まず全初期未達を分母とする率を見て、モデル・タスク・出典別の内訳と少数分母を確認する。別のタスク・モデルや同じ例の再生成で同じ結果が得られることは保証しない。

schema 2.0と2.1の診断文処理差、実施時期、seedブロックが含まれる。後続roundの生成コードは条件ごとに異なり、同じ初期コードの対応付き比較でも、成功の差を説明・実行結果提示の単一要素に帰属させない。一般的優劣・統計的有意差は断定しない。Pは別プロンプトからの独立生成であり、このF/D比較の対象外。

## 出典と再現

[前段の層別分析](../model_difficulty_seed_20261013/README.md)と同じ検証済み固定出典を使用した。新規生成・生成コードの再評価を行わず、元の生データ・評価値は保持した。

comparisons.csv：全初期未達の対応付き結果。discordant_cases.csv：片方だけで救出した例と元recordのhash。round_trajectories.csv：これらのF/D修正履歴の評価・分類・コードhash。公開ファイルに生成コード・生の例外メッセージ・認証情報は含めない。manifest.jsonに出典とhash、sanity_report.jsonに集計検証を保存。

```bash
.venv/bin/python -m scripts.analyze_discordant_repairs \
  --analysis-manifest docs/analysis/model_difficulty_seed_20261013/manifest.json \
  --out-dir docs/analysis/<新しい保存先>
```
