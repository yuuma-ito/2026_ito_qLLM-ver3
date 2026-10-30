# 横山研究室スキルのCodex導入

2026-10-28のユーザー依頼により、横山研究室のスキルをCodexで継続利用する。
元リポジトリは [yokoyama-lab/claude-skills](https://github.com/yokoyama-lab/claude-skills)。非公開の本文・チェック表・付属コードはこの公開リポジトリへ転載しない。

固定版と各SKILL.mdのSHA-256は [設定](../../configs/lab_codex_skills.json) に保持する。
導入時に公式skill-installerで元資産を取得し、[Codex用の読み替え](lab_skill_compatibility.md)を各SKILL.mdへ追加する。元のチェック表・補助スクリプト・相対参照は保持する。
付属installerの浅いcloneで古い固定コミットを取得できない場合は、同じGitHubリポジトリからSHAを直接fetchし、コミットとSKILL.mdのhashを確認して導入する。

## 導入と確認

GitHubの認証と元リポジトリへのアクセス権、Codex付属のskill-installerが必要。
標準の導入先は `~/.agents/skills/`。元本文はユーザーのローカルにだけ保存する。

```bash
.venv/bin/python scripts/setup_lab_codex_skills.py --dry-run
.venv/bin/python scripts/setup_lab_codex_skills.py
.venv/bin/python scripts/setup_lab_codex_skills.py --check
```

このリポジトリの仮想環境がない環境では `python3` に置き換える。
skill-installerが通常の場所にないときは `--installer /path/to/install-skill-from-github.py` を指定する。
`--dest` で保存先を変更できる。ネットワークアクセス・ユーザー領域への書き込みは、実行環境の許可に従う。

同じ版の再実行は変更しない。別版・ユーザー編集済み・既存の未管理スキルは上書きしない。
更新するときは固定版とハッシュを見直し、既存版を確認したうえで別の保存先へ導入する。
導入内容とファイルhashは各スキルの `.lab-codex-source.json` に記録する。

Codexのローカルスキル配置と `$skill-name` による呼び出しは [OpenAI公式ドキュメント](https://learn.chatgpt.com/docs/build-skills) に従う。
次のターンから利用でき、一覧に現れない場合はCodexを再起動する。

## 呼び出し

| 用途 | スキル | 依頼例 |
| --- | --- | --- |
| 要旨の査読 | `$thesis-abstract-review` | 要旨と本文の目的・結論・引用を確認して |
| 学会発表 | `$slide-review` | WiNFスライドを予稿と照合して査読して |
| 卒研・修論の中間発表 | `$interim-slide-review` | 卒研6分の資料を要旨と照合して |
| 表現の点検 | `$dellm` | 意味・数値・限定条件を保って表現を点検して |
| 段階的な論文執筆 | `$scidraft-cs` | 資料を整理して次の段落を提案して |
| 量子記述・回路の技術点検 | `$quantum-review` | 量子状態の記法・回路・測定・位相・ビット順が正しいか確認して |
| 情報処理学会への投稿前査読 | `$ipsj-review` | 投稿先を確認して貢献と採録条件を査読して |
| IEICE英文論文誌A/D | `$ieice-a-review` / `$ieice-d-review` | 指定した論文誌の基準で査読して |
| ゲーム評価 | `$game-review` | 提出物を検証して根拠付きで評価して |
| 個人情報フィルターの制約確認 | `$pii-filter` | Codexでの個人情報保護の対応範囲を確認して |

`pii-filter` は設計・制約を読むための導入に限る。Claude専用フック・CLI・対応表のアクセス制御は導入しないため、Codexで自動的に個人情報を遮断・匿名化する機能は有効にならない。
実データの匿名化が必要なら、生データをモデルへ渡す前に別途ローカルの保護手段を設定する。

`quantum-review` は2026-10-30の依頼で独自作成したスキルであり，非公開の横山研究室スキルとは別に管理する。[原本](skills/quantum-review/SKILL.md)と[UI設定](skills/quantum-review/agents/openai.yaml)をこのリポジトリへ保存し，利用環境の `~/.codex/skills/quantum-review/` へ同じファイルを配置する。`configs/lab_codex_skills.json` と既存の導入処理の管理対象には加えない。

量子記述の点検では，意味の誤りと表記の改善，実験仕様による制約を分ける。点検だけの依頼で原稿を変更せず，固定プロンプトや保存されたモデル出力を修正文へ置き換えない。静的確認・小さな回路の解析・シミュレーション・全入力の証明を区別する。原稿の執筆履歴を持たない担当による確認方法もスキルに記載した。利用例は「`$quantum-review` でこの卒論の量子記述と回路を確認して」。 形式検証と独立したサンプル点検の結果は[検証記録](quantum_review_skill_validation_20261030.json)に保存する。

## この研究での運用メモ

- 査読は原稿を書いた履歴を継承しないCodexセッションで行う。査読依頼時は、独立したエージェントが使えれば原稿・規定だけを渡してもよい。修正履歴や期待する指摘を先に教えない。
- 査読だけの依頼では原稿を変更しない。ユーザーが指定した修正はその指定を承認として扱い、同じ承認を取り直さない。
- 新しく執筆するときの段階的承認と、すでに指示された修正を実行することを区別する。
- 題目、保存設定、集計値、成功判定は既存の指示に従う。表示名を変えた失敗類型と保存キーを混同しない。
- 要約・本文・要旨・スライドの目的、B4の位置づけ、L3成功の意味と評価範囲、固定出典の使い分けを照合する。
- 元スキルの `thesis-abstract-review` は修論要旨を主対象にしている。卒研へ適用するときは卒研の提出様式を優先し、修論専用要件を一律に要求しない。
- `dellm scan` はローカル検出。候補だけで誤りや生成AIの使用を断定しない。`dellm review` は別のCodex呼び出しを行うため、公開可能な対象だけを隔離した作業先に置く。
- スキルを導入しただけで原稿が査読済みとは扱わない。独立査読・書き換えの実行は別の依頼で行う。

## 検証

```bash
.venv/bin/python -m pytest tests/test_lab_codex_skills.py -q
.venv/bin/python scripts/setup_lab_codex_skills.py --check
```

公開するのはこの手順、互換処理、固定版の情報、独自のテストに限る。
導入時の元本文や査読ログは `.cache/` とユーザー専用領域に置き、Gitへ追加しない。
