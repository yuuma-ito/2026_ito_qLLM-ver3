# Qiskit LLM Code Generation Harness

最新の共有原稿は[中間発表PDF](docs/midterm2026/paper.pdf)と[WiNF下書きPDF](docs/winf2026/paper.pdf)です。2026-10-13の更新で、検証済み3モデル1,500件、5モデル2,500件、2モデル補完1,000件と記述的統合集計5,000件を反映し、L0〜L3の累積達成、最終到達段階、介入前後の移動、初期成功と救出、構造検証の範囲を整理しました。[固定出典・詳細表](docs/presentation_sources/20261013T_pooled_verified/README.md)からCSV・スナップショット・検証状態を参照できます。補完実験は再分類と全件検証が完了しました。統合値は診断文の処理差を含む記述的結果として扱います。

[モデル・難度・seed別の介入効果分析](docs/analysis/model_difficulty_seed_20261013/README.md)では、検証済み5,000件の救出・部分改善・段階低下を、統合と元実験別に比較できます。FとDの救出数は全体でともに191件ですが、共通149件、Fのみ42件、Dのみ42件であり、同じ救出数でも対象例は異なります。

[FとDの片方だけで救出した例の比較](docs/analysis/feedback_debugging_discordant_20261013/findings.md)では、各42件を失敗類型・タスク・モデル・出典別に整理し、修正履歴と4例の保存コードを確認しました。import失敗と構文エラーで方向が異なり、出力表現への評価感度も記録しています。

[修正介入の救出と追加生成コスト](docs/analysis/repair_costs_20261013/findings.md)では、共有初期生成を除いた修正コスト、未救出例のコスト、F/Dの対応付き比較とPの独立生成を整理しています。記録全体ではFとDはともに191件を救出し、Fの追加tokensは約13.7%、要求時間は約19.1%少ない結果でした。

実験完了後の自動下書きは、`scripts.draft_after_experiment` がCodexを1回起動し、中間発表・学会原稿・進捗報告の更新版を `docs/completion_drafts/<保存先のhash>/` に作成します。`configs/slack_progress.cron` の専用行で5分ごとに確認し、元プロセスの終了・共有ロック解放・全件記録を待ちます。API障害や検証不備が残る場合は暫定資料として明記します。既存原稿は参考コピーとして保持し、固定スナップショットを出典にPDFを作成します。作成完了後は既存のSlackbot DMへのメール経路で進捗報告本文とローカル保存先を通知します。PDFの添付・学会投稿・Git操作はこの処理には含めません。

起動にはログイン済みの `/home/23tc011/.local/bin/codex` を使用します（[Codexの非対話実行](https://developers.openai.com/codex/noninteractive)）。状態は `.cache/draft_jobs/`、起動ログは `logs/draft_after_experiment.log` と `logs/draft_codex_*.log` に保存します。AI失敗・中断や通知失敗の自動再試行はありません。状況を確認してから必要な場合のみ `--retry` で明示的に再実行してください。完了条件の手動確認には、同じ保存設定を指定した `--dry-run` を使用します。

## seed 0〜19への実験補完と統合

残り2モデル（`qwen2.5-coder:7b`・`gemma3:4b`）のseed 0〜9を、[configs/shared_two_models_seed0_9_full.json](configs/shared_two_models_seed0_9_full.json)で1,000件の収集・検証を完了しました。既存3モデルのseed 0〜9（1,500件）と既存5モデルのseed 10〜19（2,500件）を合わせ、各モデル1,000件、合計5,000件の公開用集計を作成しました。

```bash
.venv/bin/python -m scripts.automate_experiment --config configs/shared_two_models_seed0_9_full.json --new-run --pool-config configs/shared_five_models_pool.json
```

[configs/shared_five_models_pool.json](configs/shared_five_models_pool.json)は既存の出典と統合先を指定します。検証済みの生データから集計し直し、元実験の保存設定・記録を保持します。統合先は `results/shared_five_models_pooled_seed0_19/` です。出典別の内訳は `summary_by_source.csv`、記録の照合は `sanity_report.json`、設定・出典・制約は `manifest.json` と `pool_report.md` に保存します。統合先に生データや生成コードは公開しません。

介入カタログは実験終了時に全件から再生成し、公開前に値を照合します。追加5モデル実験の古いカタログは途中集計で分母137件でしたが、全2,500件からの再生成によりbaselineのL2失敗288件と一致しました。固定した旧発表資料の出典は当時の状態として保持します。

旧3モデル実験と追加実験ではエラー分類処理の版が異なり、実行結果を与える介入の診断文にも影響します。統合値は混合手順の記述的結果として扱い、実験別・seedブロック別の内訳を残します。詳細は[統合方針と処理差の確認](docs/seed0_19_integration.md)を参照してください。

## ファイルの役割案内

初めて読む場合は、このREADMEで使い方を確認し、発表資料のPDF、実験レポート、集計CSVの順に見ると結果を把握できます。

### 設定・実行・通知

| ファイル | 役割 |
| --- | --- |
| [README.md](README.md) | 実験の実行方法、結果の読み方、通知・資料作成の使い方を説明する入口です。 |
| [AGENTS.md](AGENTS.md) | AIが作業するときに守るルールです。実験後の検証・公開・資料作成の手順を定めています。 |
| [configs/slack_progress.cron](configs/slack_progress.cron) | 進捗通知、実験監視、レポート更新、完了後の資料作成を定期実行する設定です。 |
| [configs/reviewed_experiments.json](configs/reviewed_experiments.json) | 確認済みの過去実験を記録し、定期通知で繰り返し表示しないための設定です。再開した実験は表示します。 |
| [scripts/draft_after_experiment.py](scripts/draft_after_experiment.py) | 実験の終了を確認し、AIによる発表資料の下書き作成と進捗通知を行います。 |
| [scripts/monitor_experiments.py](scripts/monitor_experiments.py) | 実験が動いているか、停止・異常がないかを監視します。 |
| [scripts/notify_progress.py](scripts/notify_progress.py) | 実験の件数や状態をまとめて通知します。 |
| [tests/](tests/) | 実験・検証・通知・資料作成の処理が想定どおり動くかを確認するテストです。 |

### 実験結果・集計

[docs/experiment_report_draft.md](docs/experiment_report_draft.md)は、実験の進捗と結果を日本語でまとめたレポートです。[docs/experiment_report_snapshot.json](docs/experiment_report_snapshot.json)は、そのレポートと同じ集計時点の数値と出典を保存します。

実験ごとの結果は `results/<実験ID>/` に保存します。今回完了した5モデル追加実験の保存先は [results/shared_five_models_full_20261010T041019864060Z/](results/shared_five_models_full_20261010T041019864060Z/) です。

| ファイル | 内容 |
| --- | --- |
| `experiment_config.json` | 実際に使ったモデル、条件、タスク、seedなどの保存設定です。 |
| `summary_by_*.csv` | モデル別・条件別・タスク別・難度別の成績表です。 |
| `rescue_rates_by_error.csv` | baselineで失敗したコードが、介入によってどれだけ成功に変わったかを失敗原因別にまとめます。 |
| `baseline_regressions.csv` | baselineでは成功していたのに、介入条件では失敗したケースを記録します。 |
| `degradation_cases.csv` | 修正型の介入で、初期roundより最終roundの評価段階が低下したケースを記録します。 |
| `failure_stage_summary.csv` | 最終結果について、どの段階で何が原因で失敗したかを集計します。 |
| `cost_runtime_summary.csv` | トークン使用量、実行時間、コード行数、回路の規模などの集計です。 |
| `timeout_summary.csv` | タイムアウトの件数・割合を集計します。 |
| `intervention_catalog_by_error.csv` | baselineの失敗原因別に、各介入の効果を比較する集計です。分析前に他の集計との分母の一致を確認します。 |
| `manifest.json` | 実験設定や実行環境、完了時刻など、再現性を確認するための記録です。 |
| `sanity_report.json` | 記録に欠落・重複・整合性の問題がないかを確認した結果です。 |
| `automation_report.json` | 自動公開に必要な検証を通過したかを記録します。プッシュ成功そのものを示すファイルではありません。 |

### 発表資料・固定した出典

現行共有版は `docs/midterm2026/` と `docs/winf2026/` に保存しています。固定出典は [docs/presentation_sources/20261013T_pooled_verified/](docs/presentation_sources/20261013T_pooled_verified/README.md) です。[完了後の初版下書き](docs/completion_drafts/9b253632951b3656d9a72a97/)は当時の出典とともに保持しています。

| ファイル・フォルダ | 内容 |
| --- | --- |
| [midterm2026/paper.pdf](docs/midterm2026/paper.pdf) | 中間発表用の現行共有資料です。 |
| [winf2026/paper.pdf](docs/winf2026/paper.pdf) | 学会発表に向けた現行原稿の下書きです。 |
| 各フォルダの `paper.tex` | PDFの元原稿です。本文や表を修正するときに使います。 |
| 各フォルダの `winf-paper.sty` | PDFの文字や段組みなどの体裁を指定するLaTeX用の設定です。 |
| 各フォルダの `progress_report_draft.txt` | 完了した作業、結果、残る課題を説明する進捗報告です。 |
| 各フォルダの `README.md` | 資料の対象実験、出典、検証状況、PDFの作成方法などを説明します。 |
| `winf2026/abstract.txt` | 学会原稿の内容を短くまとめた抄録です。 |
| 固定出典の [results_snapshot.json](docs/presentation_sources/20261013T_pooled_verified/results_snapshot.json) | 資料作成時点の数値と集計・設定・検証結果を保存します。継続更新するレポートと区別します。 |
| 固定出典の [validation_report.json](docs/presentation_sources/20261013T_pooled_verified/validation_report.json) | PDFの体裁と結果表を集計数値と照合した記録です。 |
| 固定出典の [source_manifest.json](docs/presentation_sources/20261013T_pooled_verified/source_manifest.json) | 元ファイルと公開用コピー・派生集計のhashを保存します。 |
| 旧初版下書きの `reference/` | 旧資料を参考用に保存しています。 |

現行共有版は、追加実験のカタログの分母288件が全件のbaseline失敗数と一致することを確認済みです。旧初版下書きの分母137件は途中集計として保持し、現行版の確定結果には用いません。実行時の処理差と構造検証の範囲などの限界は、各資料のREADMEと固定出典に記載しています。

## 概要

量子回路コードの生成において、モデル・タスク難度・誤り種別・介入条件ごとに、生成品質と介入効果を比較する研究用ハーネスです。生成した Qiskit コードを実行・評価し、JSONL と分析 CSV に記録します。

このリポジトリは新ハーネス仕様に基づく実験用です。APIヒントの ablation、H0〜H3、exp4 は実装対象に含みません。詳細は [docs/new_harness_spec.md](docs/new_harness_spec.md) を参照してください。

## 対象モデル・タスク・条件

**次回以降のモデル**（config上は `model_spec`、Ollamaに渡す際は `ollama:` を外した名前を使用）:

- `ollama:qwen3.5:4b`
- `ollama:gemma4:e4b-it-qat`
- `ollama:qwen3.5:9b`
- `ollama:qwen2.5-coder:7b`
- `ollama:gemma3:4b`

ユーザー提示の5モデルのサイズ・量子化・参考生成速度は、[実験レポートのモデル一覧](docs/experiment_report_draft.md)と[保存記録](docs/model_inventory_20261008.json)に整理しています。起動済みの本実験は従来の3モデルで完了させ、次回から上記5モデルを対象にします。追加の2モデルは中間発表の予備実験との対応を記録しています。SF3上で5モデルの存在を確認した情報は[サーバ取得記録](docs/sf3_model_inventory_20261008.json)に保存しています。

**タスク**：T1，T2，T3a，T3b，T4，T5，T6，T7，T8，T9 の計10タスクです。難度は次のように分類します。

| 難度 | タスク |
| --- | --- |
| easy（易） | `T1_Bell`，`T2_GHZ` |
| medium（中） | `T3a_DJ_constant`，`T3b_DJ_balanced`，`T4_BV_011`，`T5_Grover_11` |
| hard（難） | `T6_QFT_001`，`T7_IQFT_001`，`T8_QPE_001`，`T9_Ansatz_001` |

Full experiments の seed は 0〜9 です。比較する条件は次の5種類です。

- `baseline`：介入なし。初回生成のみ。
- `self_refine`：自己修正。モデル自身がコードを見直して修正します。
- `execution_feedback`：実行結果フィードバック。評価器のエラーや結果を使って修正します。
- `self_debugging`：自己デバッグ。説明・原因分析・修正を行います。
- `preventive_spec`：予防的仕様プロンプト。生成前に注意事項を追加し、修正 round を行わず1回だけ生成します。

`preventive_spec` は生成前介入であり、生成後に修正する3条件とは性質が異なります。

## セットアップ

以下は各コマンドを1行ずつ実行してください。

Linux / macOS:

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

```bash
python -m pip install -r requirements.txt
```

Windows PowerShell:

```powershell
py -m venv .venv
```

```powershell
.\.venv\Scripts\Activate.ps1
```

```powershell
python -m pip install -r requirements.txt
```

Ollama を別途起動し、実験に使うモデルが利用可能なことを確認してください。設定済みの Ollama 実験ではクラウド API キーを必要としません。`.env` に実キーを保存・公開しないでください。

## Ollamaの接続設定

通常のローカル Ollama は `http://127.0.0.1:11434` を使います。何も設定しない場合もこのポートへ接続します。

s3 の共有 Ollama を使う場合、s3 から sf3 上の Ollama へ逆向き SSH トンネル経由で接続します。s3 側から見た接続先は `http://127.0.0.1:11435` です。通常のローカル Ollama の接続先 `http://127.0.0.1:11434` とは異なるため、s3 で実験する場合はトンネルが利用可能な状態であることを確認し、実験前に Linux / macOS / s3 のシェルで次を設定してください。

```bash
export OLLAMA_HOST=http://127.0.0.1:11435
```

接続先で利用できるモデルを確認します。

```bash
curl http://127.0.0.1:11435/api/tags
```

このハーネスは `OLLAMA_BASE_URL` が設定されていればそれを優先し、未設定なら `OLLAMA_HOST` を接続先として使います。どちらも未設定なら既定の `http://127.0.0.1:11434` です。Ollama の REST 確認は `/api/tags`、ハーネスの生成要求は OpenAI 互換の `/v1` endpoint を利用します。

Ollama への生成要求には `reasoning_effort="none"` と `max_tokens=1024` を付けます。API timeout は600秒、SDKの自動再送は無効です。Ollamaの接続エラーにはハーネスが5・10・20・30・30秒待って最大5回再送し、プロンプト・temperature・seedを維持します。再試行回数は各roundの `connection_retries`、方針はmanifestの `transport_recovery` に記録します。回復しない接続障害は1件の結果として保存し、その時点で実験を停止します。タイムアウトはサーバ側で処理が続いている可能性があるため自動再送せず、記録して停止します。停止後は元の記録を保持した別実験で追試します。HTTP認証エラーやモデル指定の不備は接続再試行の対象にしません。実験は1件ずつ逐次実行します。共用サーバではモデルの pull・rm・stop、`keep_alive=0`、文脈長の拡大を行わないでください。

共用の推奨モデル `qwen3.5:4b` で20件の動作確認をする場合（上記の接続先設定後）:

```bash
python -m scripts.run_experiment --config configs/shared_qwen35_quick.json
```

Windows PowerShell では次のように設定・確認できます。

```powershell
$env:OLLAMA_HOST = "http://127.0.0.1:11435"
```

```powershell
Invoke-RestMethod http://127.0.0.1:11435/api/tags
```

## Quick debug

共用サーバの実験を、テスト・生成・評価・集計・検証・コミット・プッシュまで1コマンドで実行できます（Linux / s3）。次回以降の比較対象は上記5モデルです。5モデルに同じ2タスク・2 seed・5条件を使い、1回100レコードを計画します。接続先は `http://127.0.0.1:11435` に固定し、外部APIは使用しません。

```bash
.venv/bin/python -m scripts.automate_experiment --config configs/shared_five_models_quick.json --new-run
```

`--new-run` は時刻付きの実験IDと出力先を作り、前回の結果を残して追試します。省略した場合は設定の出力先を使い、保存済みの記録をスキップして再開します。時刻付きの追試を再開する場合は、`--config results/<実験ID>/experiment_config.json` を指定し、`--new-run` を付けずに実行してください。実行計画だけを見るには `--dry-run`、コミット・プッシュを省くには `--no-publish` を付けてください。実行にはセットアップ済みの仮想環境と、origin への Git 認証が必要です。

自動公開は無関係な変更がなく、ステージが空の状態で開始してください（再開対象の集計ファイルの変更は許容します）。60分ごとに更新されるレポート本文とスナップショットは、コミット済みの出典から再計算した内容と一致する変更だけを許容し、完了時のコミットにも含めます。手書きの考察や出典指定の変更は事前にコミットしてください。起動の重複をロックで防ぎ、テスト・記録の整合性確認・API障害の確認を通過した場合だけ、設定と公開用の集計ファイルを現在のブランチにコミットして origin にプッシュします。生成コードの不正解は通常の実験結果として扱います。生データ・秘密情報・無関係な変更は追加しません。途中で失敗した場合は非ゼロの終了コードを返し、既存の記録を残します。プッシュ拒否時もローカルのコミットを保持し、強制プッシュはしません。

### Slackへの定時進捗通知

実験レポートの[下書き](docs/experiment_report_draft.md)と[集計スナップショット](docs/experiment_report_snapshot.json)は、`configs/slack_progress.cron` のレポート更新行で60分ごと（毎時0分）に更新します。手動更新は `.venv/bin/python -m scripts.update_experiment_report` です。対象はスナップショットに指定した実験で、時刻・本実験の件数・モデル別／条件別／タスク別／失敗類型別の表と検証状況を更新します。`<!-- auto:... -->` の範囲外に書いた考察は保持します。完了した簡易実験の結果が変わった場合や、重複・予定外・件数減少を検出した場合は更新を止めます。レポート更新はモデルへの生成要求・通知送信・Git操作を行いません。

このサーバでは6時間ごと、**0時・6時・12時・18時（日本時間）** に、メール経由でSlackbotとのDMへ進捗を送る設定を `configs/slack_progress.cron` に用意しています。`--overview` で全実験の保存設定と実行状態を読み、実行中の実験を先頭に、未完了・中断・検証失敗・API障害のある実験と直近の完了結果を送ります。実行中の実験がない場合も明記します。即時通知を `--notify none` で無効にした実験もこの定時レポートには含みます。無料プランに対応し、Slackアプリ・Botトークンは不要です。送信先はSlackの転送先メールアドレスで決まり、チャンネルIDは指定しません。[Slack公式手順](https://slack.com/help/articles/206819278-Send-emails-to-Slack)

Slackとメール送信の準備:

1. Slackのプロフィールアイコンから **環境設定 → メッセージ＆メディア → Slackにメールを転送する** を開き、転送先メールアドレスを取得します。
2. 取得したアドレスを、このリポジトリの `.env` に `SLACK_EMAIL_TO` として保存します。
3. 送信元メールサービスのSMTP設定を、同じ `.env` に保存します。実アドレスやパスワードはGit・チャットに掲載しないでください。

```dotenv
SLACK_EMAIL_TO=Slackで取得した転送先アドレス
EMAIL_FROM=送信元メールアドレス
SMTP_HOST=送信元メールサービスのSMTPサーバ
SMTP_PORT=587
SMTP_SECURITY=starttls
SMTP_USERNAME=SMTPログイン名
SMTP_PASSWORD=SMTP送信用パスワード
```

暗黙TLSを使うサービスでは `SMTP_SECURITY=ssl`、通常は `SMTP_PORT=465` を指定します。STARTTLS/SSLの両方式で証明書を検証し、平文での認証は行いません。組織の許可済みSMTPリレーを使う場合のみ、`SMTP_USERNAME` と `SMTP_PASSWORD` の両方を空にできます。サービスが指定する送信用パスワードやアプリパスワードを使ってください。

Gmailを使う場合は、Googleアカウントの2段階認証を有効にし、[アプリパスワード](https://myaccount.google.com/apppasswords) を作成してください。`SMTP_HOST=smtp.gmail.com`、`SMTP_PORT=587`、`SMTP_SECURITY=starttls`、`EMAIL_FROM` と `SMTP_USERNAME` に同じGmailアドレス、`SMTP_PASSWORD` に発行された16文字のアプリパスワードを空白なしで保存します。通常のGoogleログインパスワードは使用しません。アプリパスワードが表示されないアカウントでは [Google公式手順](https://support.google.com/accounts/answer/185833?hl=ja) を確認してください。

通知内容を確認:

```bash
.venv/bin/python -m scripts.notify_progress --overview --transport email --dry-run
```

`--dry-run` は表示だけで、SMTP接続を行いません。省略すると1回送信します。SMTPサーバが受理したこととSlackへの到着は別なので、初回はSlackbotのDMで到着を確認してください。`--latest` は同じ実験IDまたは時刻付き追試の最新の保存設定を選びます。特定の実験だけを通知する場合はその `experiment_config.json` を指定し、`--latest` を省いてください。通知処理はモデルへの生成要求を行いません。

定時処理のログは `logs/slack_progress.log` に記録します。登録確認は `crontab -l` で行います。既存のcronを保ち、この通知行だけを追加・変更してください。cronはサーバのシステム時刻（現在はAsia/Tokyo）に従い、`--timezone` は通知内の表示時刻の設定です。サーバが停止している間は通知できません。

```bash
cd /home/23tc011/2026_ito_qLLM-ver3 && .venv/bin/python -m scripts.notify_progress --overview --timezone Asia/Tokyo --transport email
```

通知には記録件数・残り件数・L2成功／失敗・API障害等を含む記録件数・重複・最終更新時刻を含めます。実行状態がある場合は段階・状態更新時刻・停止時刻も表示し、実行中はモデル・タスク・seed・条件を表示します。生成コードやエラー本文は送信しません。未完了の記録だけでは実行中か中断かを区別できないため、その旨を表示します。記録完了や自動検証成功はプッシュ成功を保証しません。書き込み途中の最終行は読み飛ばし、壊れた確定行や送信失敗では非ゼロで終了します。重複送信を避けるため自動再送は行いません。

Slack API・Incoming Webhook方式も、`--transport slack` で利用可能です。API方式は `--channel` と `SLACK_BOT_TOKEN`、Webhook方式は `SLACK_WEBHOOK_URL` を使います。メール方式ではこれらの設定を参照しません。

### 実験キュー・異常監視・即時通知

`configs/experiment_queue.json` に実行順の設定を登録し、キューを起動できます。付属の例は5モデル・100レコードのquick実験を2回、合計200レコードです。共用サーバへの生成要求は逐次実行します。新しい `shared_five_models_queue` を使い、以前の3モデル用キューは `configs/shared_three_models_queue.json` に保存しています。

```bash
.venv/bin/python -m scripts.run_queue --queue configs/experiment_queue.json --dry-run
.venv/bin/python -m scripts.run_queue --queue configs/experiment_queue.json
```

正常実行・検証・コミット・プッシュが完了した場合のみ次へ進みます。実行・検証・公開の失敗では停止し、後続の実験を開始しません。進捗は `.cache/queues/<queue_id>/state.json` に保存され、同じコマンドで完了済みジョブをスキップします。`new_run: true` の時刻付きIDも初回に確定して再開時に保持します。キューまたは参照設定を変更して実行する場合や、全件を新たに追試する場合は新しい `queue_id` を指定してください。

失敗したジョブの再開には明示的に `--retry-failed` を付けます。このフラグは元のAPI障害記録を削除・置換しません。記録済みAPI障害の追試は下記の別実験として準備します。公開を省く動作確認には `--no-publish` が使えますが、公開方針を変更して同じキューを再開することはできません。

実行状態・現在の段階・進捗・5秒ごとのハートビートを `.cache/run_states/` に記録します。定時のSlack通知もこの状態を読み、実行中・中断・失敗・完了・プッシュ成功を表示します。新しい状態記録がない過去の結果では、従来どおり記録だけから実行中と中断を判別できません。

```bash
.venv/bin/python -m scripts.monitor_experiments --dry-run
.venv/bin/python -m scripts.monitor_experiments --transport email --stalled-after 3600
```

`configs/slack_progress.cron` には6時間ごとの定時進捗通知に加え、5分ごとの監視を含めます。監視では完了・異常だけでなく、通知が有効なすべての実行中の実験について、現在の段階・記録件数・残り件数を6時間ごとに報告します（保存設定がまだない開始直後は実験IDと段階を報告）。同じ6時間枠内の通知は実験ごとに1回で、記録件数が増えていなくても次の枠で報告します。`--progress-interval` で報告間隔の秒数を変更できます。プロセス消失・45秒以上のハートビート停滞・1時間以上の進捗停止を判定し、異常を通知します。モデル応答が遅い場合もあるため、監視はプロセスを強制終了しません。`--stalled-after` で進捗停止の判定秒数を変更できます。

`automate_experiment` は完了・API障害・実行失敗・コミット／プッシュ失敗をメールで即時通知します。API障害の速報は最初の該当記録が書かれた時点で送ります。`--notify none` で即時通知とその実験の監視通知を無効にでき、`--notify slack` でSlack API／Webhook方式を指定できます。通常の `run_experiment` は状態を記録しますが、単体では即時通知を有効にしません。

通知障害が起きても実験結果は保持し、通知の失敗をログと `.cache/notification_events/` に記録します。同じ実行の同じイベントは1回だけ送信を試み、ネットワーク障害時の重複投稿を避けます。キューの途中で監督プロセスが終了しても、実行中の子プロセスに共有サーバのロックが保持されるため、重複実行を防ぎます。`.cache` を削除すると再開・通知重複防止の情報が失われるため、運用中は残してください。

### API障害の追試と実験比較

API接続エラー・タイムアウトを含む `(model, task, seed)` の組だけを、新しい実験IDと出力先で追試する設定を作成できます。全条件を含めて共有round 0を新たに生成し、元の `raw.jsonl` は変更しません。`import_error`・`wrong_output` など生成コードの評価失敗だけの組は対象外です。単独の原因不明エラーは、API障害の根拠がない限り対象にしません。

```bash
.venv/bin/python -m scripts.prepare_retry --config results/<元の実験ID>/experiment_config.json --out .cache/retries/retry.json
.venv/bin/python -m scripts.automate_experiment --config .cache/retries/retry.json
```

対象がなければ設定を作らず非ゼロで終了します。追試設定の `pairs` が対象の組を明示するため、taskやseedの直積により不要な組が増えることはありません。元の実験ID・設定hash・生データSHA-256を `retry_of` に記録します。追試設定作成だけではモデル呼び出しや実験実行を行いません。

正常に集計された実験には `comparison_by_condition.csv` と `comparison_report.md` を生成し、自動公開の対象に含めます。モデル・条件ごとの成功率・救済率・実行時間・トークン数を比較できます。差分は対象task/seed、条件・round数、温度、生成設定、prompt、評価環境、記録されたモデルdigestが一致し、自動検証を通過した実験の間だけ計算します。検証未完了・失敗の実験には差分を付けません。記録されていない設定の一致は保証できず、少数seedから有意差を断定するものではありません。

```bash
.venv/bin/python -m scripts.compare_experiments --out-dir results/comparisons
```

任意の出力ディレクトリを位置引数で指定すると、その実験群だけを比較します。生データや生成コードは比較レポートに含めません。

小規模確認には `configs/quick_debug.json` を使います。1モデル × 2タスク × 2 seed × 5条件で、合計20 records を計画します。

```bash
python -m scripts.run_experiment --config configs/quick_debug.json
```

実行後、JSONL が20件あることを確認します。

```bash
wc -l results/quick_debug/raw.jsonl
```

期待値:

```text
20 results/quick_debug/raw.jsonl
```

CSV の出力を確認します。

```bash
ls results/quick_debug/*.csv
```

JSONL の先頭 record を整形して確認します。

```bash
head -n 1 results/quick_debug/raw.jsonl | python -m json.tool
```

## Full experiments

次回の本実験は `configs/shared_five_models_full.json` を使用し、5モデル × 10タスク × 10 seed × 5条件、計2,500レコードを計画します。生成・評価設定は3モデル実験とそろえています。起動済みの3モデル・1,500件の設定 `configs/full_all_models.json` と各実験の保存設定は保持します。

```bash
.venv/bin/python -m scripts.automate_experiment --config configs/shared_five_models_full.json --new-run
```

旧Qwen2.5の単独設定 `full_qwen3b.json`・`full_qwen7b.json`・`full_qwen14b.json` は過去の実験用に残しています。

## 評価指標

L0〜L3は独立した点数ではなく、段階的な到達水準として扱います。各水準の達成率は、同じ評価対象の全件数を分母とし、前段階の達成を含む累積的な割合です。

- `L0`：生成コードが構文・必須インターフェースの条件を満たすか。
- `L1`：L0を満たしたうえで、回路を構築し、タスクに応じた評価処理を実行できるか。
- `L2`：L0・L1を満たしたうえで、出力分布または状態ベクトルが期待値と許容距離内で一致するか。
- `structure_match`：回路構造の妥当性。利用可能なタスク別構造条件に合うかを独立に記録します。
- `L3`：`L0`，`L1`，`L2`，`structure_match` がすべて真の場合のみ真です。

```text
L3 = L0 and L1 and L2 and structure_match
```

API 呼び出しで `api_timeout` が起きた場合は、コード品質の失敗ではなく実行安定性の失敗として記録します。timeout record の `timeout_flag` は `true` です。

## 出力ファイル

実験ごとの出力先に、主に次のファイルを保存します。

- `raw.jsonl`：条件ごとの最終結果、round 履歴、生成コード、評価値、token・実行時間、timeout 状態、round 0 と最終 round の差分を含む JSON Lines。
- `manifest.json`：実験設定・再現性に関する情報。
- `sanity_report.json`：出力 record の整合性確認結果。

各 record には `task_difficulty`，`structure_match`，`code_lines`，`gate_count`，`circuit_depth` などを保存します。round 0 と最終 round のコード差分は `code_diff_round0_final`、指標差分は `metric_diff_round0_final` です。

## 分析CSV

実験後の分析では、出力先に次の CSV を生成します。

- `summary_by_condition.csv`：介入条件別の集計。
- `summary_by_model.csv`：モデル別の集計。
- `summary_by_task.csv`：タスク別の集計。
- `summary_by_difficulty.csv`：難度別の集計。
- `rescue_rates_by_error.csv`：baseline の失敗を介入が救出した割合を失敗類型別に集計。
- `degradation_cases.csv`：修正過程での評価段階低下の一覧。
- `baseline_regressions.csv`：baseline 成功から介入失敗に変わったケースの一覧。
- `timeout_summary.csv`：`api_timeout` と `timeout_flag` の別集計。
- `cost_runtime_summary.csv`：token 数、実行時間、コード行数、ゲート数、回路深さ等の集計。

`rescued`（救出）は baseline が `L2=False` で介入後が `L2=True` のケースです。`degradation_in_rounds`（修正過程での悪化）は修正型条件内で最終 round の評価段階が初期 round より低下したケースです。対象は `self_refine`，`execution_feedback`，`self_debugging` です。`baseline_regression`（baseline 成功から介入失敗への退行）は baseline が `L2=True` で介入後が `L2=False` となったケースです。`preventive_spec` も paired 比較に含みます。

既存 `raw.jsonl` を再分析する場合:

```bash
python -m scripts.analyze_interventions results/quick_debug/raw.jsonl
```

価格設定がない場合、cost は0ではなく `null` です。

## 構造チェックと制約

既存タスク定義にある量子ビット数とゲート数範囲を利用します。タスク定義に測定数・古典ビット数・測定要否が明示されていない場合、それらを一律に0とは要求しません。分布評価では、生成回路に測定がなければ評価用コピーに測定を追加し、測定があれば既存測定を保ちます。

全タスクに対する完全なゲート種・深さ oracle はありません。等価な回路を不当に失敗にしないため、厳密なゲート列一致は要求しません。`bit_order_error`（ビット順序誤り）はビット反転後に期待分布と一致するかで判定するヒューリスティックです。それ以外の出力不一致は `wrong_output` とします。

## GitHub公開時の注意

`.env`、API キー、個人用の設定ファイル、実験結果の `raw.jsonl` を公開しないでください。`.gitignore` は `.env`，`.venv/`，`__pycache__/`，`*.pyc`，`results/**/raw.jsonl`，`logs/`，`.cache/` を除外します。公開前に追加・変更ファイルに秘密情報が含まれないことを確認してください。

## 仕様書

実験条件、record schema、失敗類型と優先順位、timeout、差分、CSV、config の詳細は [docs/new_harness_spec.md](docs/new_harness_spec.md) に記載しています。


### 失敗した段階と原因の記録

`failure_stage` は失敗した段階、`error_category` は失敗原因を表します。最終recordと各roundに両方を保存し、`exception_type`（例外型名）と `error_message`（例外メッセージ）も記録します。例外のない判定失敗では `exception_type` は空文字です。成功時は `error_category = ok`、`failure_stage = unknown`、`exception_type` は空文字とします。

段階は `parse` / `import` / `exec` / `build` / `evaluate` / `api_call` / `unknown`。原因は `syntax` / `import_error` / `interface_mismatch` / `build_error` / `wrong_output` / `bit_order_error` / `qubit_count_mismatch` / `api_timeout` / `unknown_error` です。

- 構文解析失敗は `parse` / `syntax`、トップレベルのimport失敗は `import` / `import_error`。
- `exec()` 中の存在しない属性・メソッドへの `AttributeError` は `exec` / `interface_mismatch`。GHZ seed 6 self_debugging の `result.counts` はこの分類に該当し、接続障害・タイムアウトには含めません。
- `build_circuit()` 内の例外は、トップレベルから呼び出された場合も `build` / `build_error`。戻り値が QuantumCircuit でない場合は `build` / `interface_mismatch`。
- 出力・構造の不一致は `evaluate`。モデル呼び出し障害は `api_call` で、タイムアウトの原因は `api_timeout`、それ以外の未分類障害は `unknown_error` とし、`generation_error` も保持します。

既存の原因別分析は `error_category` を使用します。追加の `failure_stage_summary.csv` は最終recordの失敗だけをモデル・条件・段階・原因・例外型別に数えます（roundは重複加算しません）。

スキーマ2.1から新規生成記録にこれらのフィールドを保存します。旧JSONLは書き換えず、読み込み時に保存済みの原因・例外メッセージ・L0/L1情報から保守的に補います。補った記録には `failure_metadata_source = legacy_inference_v1` を付け、原因を変更した場合は `original_error_category` も保持します。保存情報で特定できない段階・例外型は `unknown`・空文字です。評価結果・生成コード・seedは変更せず、再生成・再評価は行いません。稼働中の旧プロセスは旧形式の保存を続けますが、レポート・通知・集計・再検証は補完後の分類を使用します。

### 稼働中の実験を夜間に再検証・公開する

旧ハーネスで起動済みの実験に対し、完了後に現在のハーネスで集計・検証・公開を行う待機処理を用意しています。起動済みプロセスや生成中のコードには介入せず、元プロセスの終了と共有ロックの解放を待ちます。

```bash
.venv/bin/python -u -m scripts.finalize_completed_experiment \
  --config results/<実験ID>/experiment_config.json
```

夜間も動かす場合はこのコマンドをtmux等の独立セッションで実行します。60秒ごとに確認し、待機上限は既定で7日です。状態は `.cache/finalizers/`、標準出力は起動時に指定したログへ保存できます。

保存済みの同じ実験設定を使い、全件記録・重複なし・sanity check成功・API障害なしを確認してから既存自動化ラッパーをresumeします。全条件が記録済みなので追加生成は行わず、現在の分類で集計を再生成し、テスト・検証後に関連成果物をコミット／プッシュします。未完了・API障害・未分類エラーがある場合は待機終了後に停止し、欠けた生成を自動で補いません。通知は既存cronに任せ、待機処理から新たなメールは送信しません。

`exec` 段階の `QiskitError: No counts for experiment ...` は、countsも保存した状態ベクトルもないResultに `get_counts()` を呼んだインターフェース誤用として `interface_mismatch` に分類します。他のQiskitErrorを一律にこの分類へ移しません。`build_circuit()` 内で同じ例外が生じた場合は `build / build_error` です。DJ constant seed 9 の観測例と介入候補は [分類確認記録](docs/dj_seed9_failure_classification.json) に保存しました。LLMへの介入効果は未検証です。

`exec` 段階の `QiskitError: No statevector for experiment ...` は、statevector未保存での結果取得として `interface_mismatch` に分類します。保存済みの `unknown_error` は読み込み時に限定的に補正し、元分類・例外・生データ・評価値は保持します。[QPE seed 2の分類確認](docs/qpe_seed2_failure_classification.json)を参照してください。
