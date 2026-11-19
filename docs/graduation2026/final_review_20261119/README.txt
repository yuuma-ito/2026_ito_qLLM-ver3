独立査読・提出前確認（2026-11-19）

対象固定版：60b68e29e0bfece77e11df201e0f92d9322f78d0
対象：卒論40ページ、要旨2ページ、スライド12枚。
判定対象と保存先を固定し、執筆履歴を渡さない3担当が独立に査読した。査読資料は同commitから取り出した147ファイルと確認基準1ファイル。生API応答・生成コード全文・非公開checkpoint・非公開スキル本文は配布・公開していない。
原稿自体は変更していない。指摘への修正は今回の確認依頼の範囲に含めない。

依頼3：独立査読は完了
卒論：重大0、要修正1、推奨2。本文40ページ通読、17ページ画像確認。
要旨：重大0、要修正0、推奨3。全2ページ画像確認。
スライド：致命0、重要0、推奨4。全12枚画像確認。
各担当は公開CSV・設定・記録と照合した。採点の正当性やrawからの全件再評価まで保証する査読ではない。

優先する訂正
卒論p23・4.4節の難度別F/Dの救済数に、転記不一致が1件ある。
現状：「易22/69組・25/69組，中79/225組・79/225組，難82/251組・76/251組」
訂正案：「易22/69組・25/69組，中79/225組・78/225組，難82/251組・76/251組」
Fの中79は正しい。後者のDのみ78へ訂正する。Dは易25＋中78＋難76＝179。
固定paired_records.csv全4,000行とrepair_summary.csvが一致する。主結果のD179/545、最終634/1,000と各表は正しく、元データや集計を180へ変える必要はない。
確認記録：confirmed_numeric_discrepancy.json

推奨の要点（採否は別途判断）
・卒論：補足manifestへの追跡先を明示、指定出力と算法全体の違いを具体例で補助。
・要旨：WordとTeXの節直後の字下げ差、文献の参照版の明示、結論でコスト軸を短く回収。
・スライド：6分の実測と短縮案、方法図で保存履歴＋部分追試を明示、背景見出しの観測範囲、補足文献の投影方法。
上記を正式規定違反や必須の追加実験とは判定していない。詳細な根拠・修正案・未確認範囲は各独立報告を参照する。

依頼4：現環境で可能な確認は完了。Office本番表示と学科規定の照合は未完了
portable検査26項目はすべて成功。PDFのページ数・用紙・文字のページ外はみ出し・フォント埋込、Wordの指定フォントと11pt宣言、要旨の複製一致等を確認した。
フォントを宣言したことと、指定フォントで描画したことは別である。指定フォントはローカル未導入。接続中のWord/PowerPointセッションもなく、Microsoft製品上の描画・最終PDF出力は実施できていない。
ユーザー回答によれば学科要領はWebClass限定。認証済みの学科要領・正式テンプレート原本は未取得であり、その完全適合は未確認。
大学の公開全学案内は確認した。現行卒論PDFは約1.59MBで、全学案内の100MB制限と従来のローカル目標10MBを満たす。ただし、学科内の要旨・スライド・ファイル名・締切等の規定を代替する確認ではない。
全学案内：https://office.nanzan-u.ac.jp/KYOUMU/course-class/course06.html
2026年度秋学期案内：https://office.nanzan-u.ac.jp/KYOUMU/course-class/item/2026fall_Graduation_Thesis_Announcement.pdf
全学案内での理工学部受付は2026-12-01 09:00〜2027-01-30 17:00（日本時間）、大学提出はPORTA。学科内のWebClass手続きとは区別する。

保存ファイル
independent_thesis_review.txt：卒論の独立査読
independent_abstract_review.txt：要旨の独立査読
independent_slides_review.txt：スライドの独立査読（想定質問・回答骨子付き）
input_manifest.json：査読対象commit・ファイルhash・独立担当の記録
independent_slides_input_hashes.json：148ファイルの集合hashと個別一覧
submission_checks.json：portable検査結果と環境の不足
check_submission.py：原稿を変更しない再検査スクリプト
confirmed_numeric_discrepancy.json：D中難度の個別再計算
results_manifest.json：報告ファイルのhashと依頼ごとの状態
confirmed_numeric_discrepancy.json以外の独立査読にも、実施した読解・画像・CSV確認範囲をそれぞれ記載。
office_sessions.json：接続文書セッションの検査結果
official_sources.json：公開全学案内とWebClass限定資料の未確認状態
office_final_check_steps.txt：指定フォントを備えたOfficeで残っている確認手順（未実施）

再実行
リポジトリ直下で
PYTHONPATH=.cache/acknowledgments_tools .venv/bin/python docs/graduation2026/final_review_20261119/check_submission.py
このスクリプトは独立査読やMicrosoft Office表示確認を再実行するものではない。
