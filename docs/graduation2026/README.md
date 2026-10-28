# 卒業研究発表会用の原稿・発表資料

題目：**量子LLM支援プログラミングにおける失敗類型と介入カタログの実証研究**。今後の更新でもこの表記を使用する。

2026-10-22にB4追加実験の完了結果を要旨と論文本体へ反映した．B4は同じ初期1,000組を用い，初期失敗545組から217組（39.8%）が成功，最終成功672組（67.2%）であった．論文には比較方法・全体／モデル別／初期失敗類型別の表・成功対象の重なり・追加消費・限界と今後の課題を追加した．[固定出典](../analysis/independent_4_completed_20261022/source_manifest.json)に保存設定・集計・検証状態を記録した．要旨は[midterm2026](../midterm2026/README.md)の現行原稿と同じ内容に同期した．スライドは従来版を保持しており，B4未反映．

2026-10-16版の到達経路と2026-10-22固定のB4追加実験に基づく草稿。指導教員の確認と本人による推敲を経て提出する。

| 資料 | 編集用 | 閲覧用 |
| --- | --- | --- |
| 卒業論文本体（表紙・要約・目次・付録を含む26ページ） | [thesis.docx](thesis.docx) | [thesis.pdf](thesis.pdf) |
| 要旨（個人研究・2ページ） | [abstract.docx](abstract.docx) | [abstract.pdf](abstract.pdf) |
| 発表スライド（本編8枚・補足3枚） | [slides.pptx](slides.pptx) | [slides.pdf](slides.pdf) |

[発表の要点メモ](speaker_notes.txt)は本編合計360秒の配分。PowerPointの各ページにも同じ要点を発表者ノートとして格納した。原稿の読み上げには使わず，スライドを見て自分の言葉で説明する練習に用いる。実際の発表時間はリハーサルで確認する。発表6分・質疑3分を想定している。

## 2026-10-28の図追加・用語整理（現行版）

現行PDFは26ページ・9表・3図。研究の題目と固定実験結果は保持した。

- 図1：共有初期生成からR/F/D/B4への分岐、最大3回の追加生成と成功時停止、集計までの論理的手順（第3章）。Pは初期生成前から分岐する点線の独立経路として示し、保存履歴と追試に基づく集計であることを本文へ明記した。
- 図2：初期失敗545組に対するR/F/D/B4の追加成功率（第4章）。R/F/Dの救済とB4の独立再生成を区別する。
- 図3：Fのみ43組・共通140組・Dのみ40組・双方未救済322組を、件数に比例する帯で表示（第4章）。
- 付録8.1.1〜8.1.3を、それぞれ「5モデル追加実験」「3モデル本実験」「2モデル補完実験」の保存設定へ改題。
- 要約と本文冒頭に初期組・主L3・到達履歴を定義し、prefix/suffixの混在表現を日本語化。「追加消費」は「追加計算コスト」へ統一した。

研究目的に修正介入と独立再生成B4の比較を明記し，介入の定義を生成前Pと生成後R/F/Dを含む表現へ修正した。B4は修正指示を与えない対照条件として区別した。「検証済みの保存済みの」などの重複表現を整理し，図2のキャプションを簡潔にした。

図は [thesis_figures.py](thesis_figures.py) が固定CSVから生成する。Wordには高解像度PNGを埋め込み、再利用用に [フローチャートPDF](figures/experiment_flow.pdf)・[追加成功率PDF](figures/additional_success_rates.pdf)・[F/D重なりPDF](figures/fd_overlap.pdf) と各SVGも保存した。[図の出典・数値](figures/figure_manifest.json)、[図の検証記録](figure_validation_report_20261028.json)から生成元を確認できる。

```bash
PYTHONPATH=.cache/graduation_plot_tools:.cache/graduation_tools .venv/bin/python docs/graduation2026/thesis_figures.py
PYTHONPATH=.cache/graduation_tools .venv/bin/python docs/graduation2026/validate_figures.py
```

図の生成にはMatplotlib（今回3.11.2）とIPAexGothicを使用した。この環境では `.cache/graduation_plot_tools/` に依存を配置した。図の元CSV・生成コード・画像のhashを記録し、図番号はWordのSEQ、本文の参照はREFフィールドとした。キャプションは図の下へ配置する。用語の共通処理は [thesis_language.py](thesis_language.py) に保持する。

## 2026-10-28の構成・体裁の見直し（図追加前の履歴）

ユーザーの6点の指摘に基づき、重複を整理した25ページ版へ更新した。本文は25,938字（第1〜6章、見出し・目次・表セルを除く）。分量を増やした直前の35ページ版は下記の拡充履歴として区別する。

- 目次と本文の間の白紙を削除。表紙を1とする通し番号を維持し、5ページ目から本文を開始する。
- 第4章を15節から7節へ、第5章を17節から5節へ統合。モデル・類型・追加消費の数値と説明をそれぞれ一か所へまとめた。
- R/F/DとB4の重複表を統合し、表は12から9へ。モデル・失敗類型・タスクを同じ列順で比較する。
- 表の「保存分類unknown」を「その他（未定義変数）」へ短縮。元CSVのunknown_errorキーと件数は維持する。表の分類列幅を56mmとし、見出しも短縮した。
- 本文は左揃え、表の説明・分類名は左揃え、数値は右揃えとし、両端揃えによる不自然な字間伸長を避けた。
- 第3章を「評価・実験方法」へ改題。資料作成・変更管理・提出前確認は本文・付録から外し、[作業メモ](work_notes.txt)へ移動した。

[構成整理の検証記録](revision_report_20261028.json)に直前版との比較、全本文段落の収録、引用順、集計との一致を記録した。空白なし・通し番号・目次・9表の整合・段落配置は [validation_report.json](validation_report.json)、現行PDFの画像確認は [thesis_visual_review.json](thesis_visual_review.json)を参照。

## 2026-10-28の本文大幅拡充（構成整理前の履歴）

ユーザー指示により、ページ数を上限にせず卒論本文を拡充した。表紙・要約・目次・付録を含むPDFは18ページから35ページになった。第1〜6章の本文（見出し・表セル・目次を除く）は10,117字から42,602字へ約4.21倍、82段落から273段落へ増加した。全段落の文字数は49,401字で、目次は94項目・2ページである。目次後の意図した空白ページは5ページ目に保持した。

追加した内容は、コード生成支援における失敗後の意思決定、自己修正と外部情報の関係、量子状態・測定分布・大域位相・指定入力評価の原理、段階評価・到達可能な履歴再構成、全モデル・全タスク・初期失敗類型の詳解、B4/F/Dの成功集合、未成功消費と停止、介入カタログの項目案、内的・構成概念・外的妥当性、今後の比較実験の設計、結論と利用時の含意である。

固定実験結果と既存の12表は維持し、B4表を説明の直後へ配置した。新しい実験は行わず、観測結果、説明用の想定例、考察上の仮説、未実施の計画を区別した。文献は7件とし、追加文献を含む原論文公開ページの確認範囲を [bibliography_sources.json](bibliography_sources.json) に記録した。

この時点の [拡充記録](expansion_report_20261028.json) は35ページ版に対応し、現行版の検証結果とは区別する。本文の生成元は [thesis_expansion.py](thesis_expansion.py)。[拡充検証記録](expansion_report_20261028.json)には更新前後の量、全261本文段落のPDF収録、引用順、層別集計とB4交差の照合を記録した。[validate_expansion.py](validate_expansion.py) は次で再実行できる（現在は現行版のrevision_report_20261028.jsonへ出力する）。

```bash
PYTHONPATH=.cache/graduation_tools .venv/bin/python docs/graduation2026/validate_expansion.py
```

書式と画像確認は現行版の各検証記録を参照。PDFは従来と同じ代替フォントの確認版であり、指定フォントを備えたMicrosoft Wordでの最終表示確認は残る。

## 形式と内容

要旨はA4，左右18mm，上18mm，下24mm，題目・著者は1段，本文は2段。本文・表・見出し・題目は11ポイント。ページ番号を付け，白黒で作成した。日本語の句読点は「，」「．」を用い，表キャプションを上に置いた。参考文献は初出順の番号で参照する。図を追加する場合は番号とキャプションを下に付け，本文から参照する。

卒業論文は2026-10-20にユーザーが提示した「卒論テンプレート_ver.1.2_260430.doc」の解析内容に合わせて再生成した。A4縦・上下面30mm・左右20mm・1段組み，本文は日本語MS 明朝／英数字Centuryの10.5pt，見出しは日本語MS Pゴシック／英数字Arialの18・14・12ptをWordに設定した。表紙は2023TC011 伊藤 悠真，指導教員 横山 哲郎，提出年月2027年1月とし，要約ページの所属はユーザー指定どおり「南山大学 理工学部 電子情報学科」とした。別ファイルの要旨・スライドの書式は今回変更していない。

表紙・要約・自動目次の後は，次ページから本文を開始する。ユーザー指示により目次後の意図的な白紙は廃止した。本文は「はじめに」「関連研究」「評価・実験方法」「結果」「考察」「おわりに」の6章，続いて参考文献と付録とした。旧原稿の方法・実装・実験設定は第3章の節・小節にまとめた。Heading 1〜3と連動する多段階番号，TOCフィールド，表紙から連続する右寄せPAGEフィールド，表のSEQ番号と本文のREF参照を設定した。目次69項目の表示ページをPDFと照合した。題目は2026-10-25のユーザー指定により「量子LLM支援プログラミングにおける失敗類型と介入カタログの実証研究」に固定した。

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
python docs/graduation2026/validate_template.py
```

[template_thesis.py](template_thesis.py) が書式を適用する。[convert_thesis.py](convert_thesis.py) はLibreOfficeで卒論をPDF化し，実際の見出し位置から `toc_cache.json` を更新してページが一致するまで再出力する。WordのTOCフィールドは編集後も更新できる。キャッシュは現行PDF用であり，Wordでの再ページ割付後は目次を再更新する。

[validate_template.py](validate_template.py) は余白・フォント指定・見出し番号・目次・ページ番号・表の元CSVとの一致・出典hash・PDF全ページの文字境界とフォント埋込みを確認する。[validation_report.json](validation_report.json) の今回の検証対象は卒論Word・PDFであり，要旨はmidterm2026の検証記録を参照する。[thesis_visual_review.json](thesis_visual_review.json) は実際に確認したPDFのhashとページ一覧を保持する。原本照合とMicrosoft Wordでの確認は未実施として記録する。以前の一式と検証記録はローカルの `.cache/graduation_template_before/` に保持している。

## 提出までに残る確認

- 正式な卒論題目の承認。英語版を別途提出する場合は，著者名・指導教員名・所属の正式英語表記。
- 指導教員による本文，題目，引用・参考文献書式の確認。学部の当該年度の正式テンプレートは今回未取得であり，ユーザーが転記したテンプレート解析結果に基づく。原本の表紙配置と段落スタイルの確認を残す。
- 剽窃チェックと類似レポートの作成。要旨の審査用・最終版のそれぞれで提出する。今回その検査を実施したとは扱わない。
- 提出先WebClassの最終要領，卒業論文PDFの10MB以下，Word・PowerPoint上での最終レイアウト，6分発表と質疑の練習。

既存の中間発表・WiNF原稿と，作業開始時点の実験レポート変更は保持した。今回の作業では追加実験，モデル要求，生成コードの実行，通知，投稿，外部アップロード，Git操作は行っていない。

B4は表3〜6・表8へ統合した．主L3・初期コードは共通でも，最大要求回数の一致は入力情報・tokens・実行時期の一致を意味しない．B4は独立再生成による成功，R/F/Dは修正介入による救済として区別し，因果効果・統計的有意差を主張しない．
