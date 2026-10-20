# 卒業研究発表会用の原稿・発表資料

2026-10-16版の検証済み固定集計に基づく初稿。指導教員の確認と本人による推敲を経て提出する。

| 資料 | 編集用 | 閲覧用 |
| --- | --- | --- |
| 卒業論文本体（表紙・要約・目次・空白ページ・付録を含む17ページ） | [thesis.docx](thesis.docx) | [thesis.pdf](thesis.pdf) |
| 要旨（個人研究・2ページ） | [abstract.docx](abstract.docx) | [abstract.pdf](abstract.pdf) |
| 発表スライド（本編8枚・補足3枚） | [slides.pptx](slides.pptx) | [slides.pdf](slides.pdf) |

[発表の要点メモ](speaker_notes.txt)は本編合計360秒の配分。PowerPointの各ページにも同じ要点を発表者ノートとして格納した。原稿の読み上げには使わず，スライドを見て自分の言葉で説明する練習に用いる。実際の発表時間はリハーサルで確認する。発表6分・質疑3分を想定している。

## 形式と内容

要旨はA4，左右18mm，上18mm，下24mm，題目・著者は1段，本文は2段。本文と表は10ポイント，見出し10.5ポイント，題目11ポイント。ページ番号を付け，白黒で作成した。日本語の句読点は「，」「．」を用い，表キャプションを上に置いた。参考文献は初出順に[1]，[2]，[3]とした。図を追加する場合は番号とキャプションを下に付け，本文から参照する。

卒業論文は2026-10-20にユーザーが提示した「卒論テンプレート_ver.1.2_260430.doc」の解析内容に合わせて再生成した。A4縦・上下面30mm・左右20mm・1段組み，本文は日本語MS 明朝／英数字Centuryの10.5pt，見出しは日本語MS Pゴシック／英数字Arialの18・14・12ptをWordに設定した。表紙は2023TC011 伊藤 悠真，指導教員 横山 哲郎，提出年月2027年1月とし，要約ページの所属はユーザー指定どおり「南山大学 理工学部 電子情報学科」とした。別ファイルの要旨・スライドの書式は今回変更していない。

表紙・要約・自動目次の後に，原本の説明にある空白ページを1枚保持した。本文は「はじめに」「関連研究」「提案手法」「結果」「考察」「おわりに」の6章，続いて参考文献と付録とした。旧原稿の方法・実装・実験設定は第3章の節・小節にまとめた。Heading 1〜3と連動する多段階番号，TOCフィールド，表紙から連続する右寄せPAGEフィールド，表のSEQ番号と本文のREF参照を設定した。目次51項目の表示ページをPDFと照合した。正式な題目は未承認のため，既存草稿の研究題目を保持している。

原本そのものは未取得であり，原本との完全一致や大学正式規定への適合を確認したものではない。表紙の縦位置，見出しの間隔・位置・太字，目次の細かな設定など，補完した値は [format_spec.json](format_spec.json) に記録した。本文の行間と段落前後間隔は固定値を置かず，全段落共通の字下げも追加していない。サーバーにMS 明朝・MS Pゴシック・Centuryがないため，PDFは代替フォントによる確認版であり，指定フォントを備えたWordで最終確認する必要がある。

スライドは16:9，白背景，グレーと黒を基本にし，1枚1メッセージとした。棒グラフ，図形，文字はPowerPointで個別に編集できる。使用フォントはIPAexMincho／IPAexGothic。PDFにはフォントを埋め込んだ。編集するPCに同フォントがない場合は置換で改行が変わるため，フォントを用意するか，Word／PowerPointで代替フォントとページ割付を確認してから書き出す。

## 集計の根拠

主出典は[2026-10-16版固定発表出典](../presentation_sources/20261016T_reachable_rescues/README.md)。集計時点は`results_snapshot.json`の`captured_at_utc`をそのまま[source_manifest.json](source_manifest.json)に記録した。今回読み取った固定ファイルのSHA-256も同manifestに保持している。

1,000初期組・5,000条件記録，初期成功455組・失敗545組。救済はR96/545（17.6%），F183/545（33.6%），D180/545（33.0%）。F/D共通140組，Fのみ43組，Dのみ40組，双方未救済322組。表は[全分母CSV](../analysis/reachable_rescues_20261016/core/repair_summary.csv)と固定スナップショットから生成した。[詳細分析](../analysis/reachable_rescues_20261016/README.md)には履歴・追加消費・3回目の寄与を保持する。

元実験は3モデルseed 0〜9（1,500条件），5モデルseed 10〜19（2,500），残り2モデルseed 0〜9（1,000）。実験IDと保存設定hashは論文付録Aに記載した。主結果は検証済み保存prefixと必要な部分追試suffix（293ケース）を反映した到達可能な経路で，全件新生成実験ではない。旧120件や過去の評価値を主結果に合算しない。出典間のschema・診断文の差を保持する。

主L3は指定入力の期待出力と所定の構造要件に限定され，全入力のアルゴリズム同値性を保証しない。共有初期・タスク・seed依存があり，モデルの一般的優劣，因果効果，統計的有意差は主張しない。追加コストは共有初期を除き未救済例の消費も含む再構成経路の計算値であり，金銭費用ではない。上限別の比較は同じ履歴を区切った集計である。

文献の書誌情報は原論文の公開ページで確認した：[Self-Refine](https://arxiv.org/abs/2303.17651v2)，[Self-Debugging](https://arxiv.org/abs/2304.05128v2)。原論文の完全再現とは位置づけない。

## 再生成と検証

生成スクリプトは[build.py](build.py)。python-docx 1.2.0，python-pptx 1.0.2で編集用ファイルを作成し，LibreOffice 24.2.7.2で同じ編集用ファイルからPDFを出力した。PDFの内容・ページ数・図表・フォントと，Officeファイルの構造の検証結果は[validation_report.json](validation_report.json)に記録する。PDF検証はPyMuPDF 1.28.2を使用した。

この作業環境では，依存ライブラリとPDF変換ツールを`.cache/graduation_tools/`と`.cache/graduation_office/`に配置した。システムへのインストールは行っていない。通常の環境では次で生成できる。

```bash
python docs/graduation2026/build.py
libreoffice --headless --convert-to pdf --outdir docs/graduation2026 docs/graduation2026/abstract.docx docs/graduation2026/thesis.docx docs/graduation2026/slides.pptx
```

卒論だけを再生成する場合は次を使う。環境に依存ライブラリがない場合は `PYTHONPATH=.cache/graduation_tools` と `.venv/bin/python` を使用する。

```bash
python docs/graduation2026/build.py --thesis-only
python docs/graduation2026/convert_thesis.py
python docs/graduation2026/validate.py
```

[template_thesis.py](template_thesis.py) が書式を適用する。[convert_thesis.py](convert_thesis.py) はLibreOfficeで卒論をPDF化し，実際の見出し位置から `toc_cache.json` を更新してページが一致するまで再出力する。WordのTOCフィールドは編集後も更新できる。キャッシュは現行PDF用であり，Wordでの再ページ割付後は目次を再更新する。

[validate_template.py](validate_template.py) は余白・フォント指定・見出し番号・目次・ページ番号・表の元CSVとの一致・出典hash・PDF全ページの文字境界とフォント埋込みを確認する。[validation_report.json](validation_report.json) の今回の検証対象は卒論Word・PDFのみである。[thesis_visual_review.json](thesis_visual_review.json) は実際に確認したPDFのhashとページ一覧を保持する。原本照合とMicrosoft Wordでの確認は未実施として記録する。以前の一式と検証記録はローカルの `.cache/graduation_template_before/` に保持している。

## 提出までに残る確認

- 正式な卒論題目の承認。英語版を別途提出する場合は，著者名・指導教員名・所属の正式英語表記。
- 指導教員による本文，題目，引用・参考文献書式の確認。学部の当該年度の正式テンプレートは今回未取得であり，ユーザーが転記したテンプレート解析結果に基づく。原本の表紙配置と段落スタイルの確認を残す。
- 剽窃チェックと類似レポートの作成。要旨の審査用・最終版のそれぞれで提出する。今回その検査を実施したとは扱わない。
- 提出先WebClassの最終要領，卒業論文PDFの10MB以下，Word・PowerPoint上での最終レイアウト，6分発表と質疑の練習。

既存の中間発表・WiNF原稿と，作業開始時点の実験レポート変更は保持した。今回の作業では追加実験，モデル要求，生成コードの実行，通知，投稿，外部アップロード，Git操作は行っていない。
