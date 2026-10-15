# 再評価の中断原因と再開

## 確認した事実

再評価の最終進捗は2026-10-15 00:38:50.805 JST（UTC 2026-10-14 15:38:50.805）。3,740/9,517 round完了、1 roundはpending。終了後のdriver.lockは未保持、再評価・通知監視のプロセスは存在しなかった。進捗JSONはrunningのまま取り残された。

ローカルCodexログ `/home/23tc011/.codex/logs_2.sqlite` のlogs表に、同じ会話threadについて次が記録されている。原ログの全内容・他会話の情報は転記しない。

- id 175303、UTC 15:38:51、`codex_app_server::request_processors::thread_lifecycle`: `has no subscribers and is idle; shutting down`
- id 175313、UTC 15:38:51、`codex_core::session::handlers`: `Shutting down Codex instance`

同時刻のdaemon.stderr.logにも会話終了に伴うMCP終了と記録先thread消失がある。その後、管理実行セッション75645へのアクセスはUnknown process idとなった。

## 判断と限界

停止の直接の契機は、接続クライアントがなく待機状態と判断されたCodex会話セッションのshutdownである。再評価と通知監視をその管理実行セッション内に置いたため、会話終了に巻き込まれたと判断する。個々の子プロセスの終了signal/exit codeは保存されていない。

tmuxを使わなかったこと自体が例外を発生させたのではなく、永続実行をCodex会話の寿命から分離していなかったことが問題である。SSH切断・クライアント終了・会話の切替のどれがsubscriber消失を引き起こしたかは、このログだけでは確定できない。親デーモンがsystemd配下、制御端末なしという先の確認だけでは子の継続を保証できなかった。

公式OpenAI documentationの[Codex Prompting Guide](https://developers.openai.com/cookbook/examples/gpt-5/codex_prompting_guide)はexec_command/write_stdinによる長時間実行を説明するが、今回の会話終了後の存続を保証する記述としては扱わない。原因判断は上記ローカルログによる。

## 再開前の検証

- checkpointのSQLite integrity_check: ok。全完了結果のhash一致を検証した。
- 保存済みmanifestと現行計画・入力出典・評価器・driverのfingerprint一致を確認した。主判定・補助判定は変更しない。
- 完了済み3,740 roundとpending 1 roundを含むDBを私的領域にバックアップした。
- 再開・隔離・checkpoint・補助評価・通知の関連テスト: 53 passed、20件のQiskit非推奨警告。テスト成功を評価妥当性全体の証明とはしない。

再開は同じcheckpointを用い、完了結果を再計算・上書きせず、処理途中の1 roundのみ回復対象とする。独立tmuxセッションで本体と通知監視を起動し、driver.lock保持、完了件数の増加、tmux親プロセスを確認する。サーバー再起動への自動再開は設定しない。

## 再開後の確認

UTC 2026-10-14 17:13:08（JST 10月15日02:13:08）に同じcheckpointから再開。本体 `qllm-reevaluation`、通知監視 `qllm-reevaluation-notify`。両方の親は既存の独立tmux server（PID 690385）、その親はsystemd（PID 1）であり、Codex配下から分離された。元の完了3,740件のresult hashを保持し、未処理分の完了件数増加とdriver.lock保持を確認した。詳細はresume_verification.json。Git pushは行っていない。
