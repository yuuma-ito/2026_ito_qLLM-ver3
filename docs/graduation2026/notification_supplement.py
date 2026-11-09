"""Small chapter 4/5 supplement from the published notification experiment."""
from pathlib import Path
import csv

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'docs/analysis/notification_ablation_20261105T164644282604Z'
TITLE = '補足実験：失敗通知と詳細診断の比較'
METHOD = (
    '失敗の通知と詳細診断の追加を分けて調べる補足実験として，既存の初期失敗545組を用い，'
    '自己点検・修正の指示を共通にした3条件を比較した．R0は従来のRから外部結果を与えない旨の一文を除き，'
    'R1はR0に失敗通知だけを，R2はR1に検証器の詳細診断を加えた．'
    '5モデル・10タスクを対象とし，temperature 0.7，出力上限1,024 tokensで，各条件に追加1回の生成を行った．'
    '表6.8に主評価のL3成功数と率を示す．全1,635要求を記録し，保存パケット照合で欠落・重複・API障害は0件であった．'
    '固定出典は公開commit 9128f4bのdocs/analysis/notification_ablation_20261105T164644282604Z/であり，'
    '実験計画，保存設定への参照，検証記録と最大3回の副評価を同フォルダに保存した．'
)
DISCUSSION = (
    '4.8節の補足実験では，追加1回の成功率は失敗通知の追加で1.10ポイント，'
    'さらに詳細診断を加えると7.16ポイント高かった．この対象では，失敗したという通知だけより，'
    '詳細診断を含む条件で成功率の改善が大きかった．ただし，同じ545組を再利用した観測であり，'
    '独立な追加標本ではない．従来のR/F/Dとは指示文が異なるため主結果と合算せず，'
    '診断による入力長の増加も含む比較として扱う．診断内容だけの効果や，'
    'モデルの内的な失敗理解，未知課題での有効性までは認定しない．'
)


def table_rows():
    with (SOURCE / 'stage1/summary.csv').open() as stream:
        rows = {r['condition']: r for r in csv.DictReader(stream) if r['grouping'] == 'overall'}
    labels = {'R0': '結果情報なし', 'R1': '失敗通知', 'R2': '失敗通知と詳細診断'}
    return [[c, labels[c], rows[c]['successes'], rows[c]['initial_failures'],
             f"{100 * float(rows[c]['success_rate']):.2f}%"] for c in labels]


def apply(chapters):
    chapters[5][1].append((TITLE, [METHOD]))
    chapters[6][1][0][1].append(DISCUSSION)
