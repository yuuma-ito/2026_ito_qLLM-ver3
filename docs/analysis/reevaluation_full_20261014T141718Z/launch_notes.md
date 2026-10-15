# 本番再評価の起動記録

ユーザーの開始指示に基づく5,000記録・9,517 roundの再評価。主v4・補助v2を維持する。全体327テストと更新後の起動処理3テストが成功した後に起動した。

最初の背景起動は、この実行環境で親コマンド終了時に終了し、初期化・評価は行われなかった。管理セッション75645で起動し直し、最初の48 round完了とdriver.lock保持を確認した。PIDは実行namespace内の値であり、別namespaceからのPIDチェックを生存判定に使わない。

実行状態はrun_status.json、私的checkpointは.cache/reevaluation/reevaluation_full_20261014T141718Z/checkpoint.sqlite3。48 roundずつ保存し、基盤失敗で停止する。完了時はfinal/、基盤失敗時はpartial/へ比較CSV・summary・sanityを保存する。実験レポートとスナップショットの再評価節を実行に合わせて更新する。

元raw・旧判定を保持し、生成コード・生例外文・checkpoint DBを公開しない。LLM要求・外部通知・自動Git操作は行わない。Git pushは行わない。

## 完了通知の追加

その後のユーザー依頼により、別プロセスでメール経由Slackbot DMへの一度限りの完了／異常停止通知を設定した。実験本体・評価器・checkpointのprofileは変更していない。通知設定はnotification_setup.json、送信状態は.cache/reevaluation_notifications/に保存する。SMTP受理とSlack到達を区別し、送信結果が不明な場合は自動再送しない。
