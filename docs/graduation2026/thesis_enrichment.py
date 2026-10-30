"""Sourced catalog, two observed cases and experiment prompts for the thesis."""
from pathlib import Path
import csv
import hashlib
import json

HERE = Path(__file__).resolve().parent


def ensure():
    manifest = json.loads((HERE/'enrichment_manifest.json').read_text())
    for name, expected in manifest['outputs_sha256'].items():
        if hashlib.sha256((HERE/name).read_bytes()).hexdigest() != expected:
            raise ValueError('Publication evidence hash mismatch: '+name)


def apply(chapters):
    history = next(ps for title, ps in chapters[5][1] if title == '成功対象の重なりと履歴分析')
    history.extend([
        'Fのみ成功した保存事例として，G4のIQFT課題（T7，seed 14）を示す．共有初期コードはQFTをqiskit.circuitから読み込もうとし，保存判定はimport失敗であった．Fの1回目の修正では読み込み先がqiskit.circuit.libraryへ変更され，L3成功となった．同時に，回路構築関数の外にあった使用例コードも削除された．',
        '修正前（Fの初期コードから抜粋）\nfrom qiskit.circuit import QFT',
        '修正後（Fのround 1から抜粋）\nfrom qiskit.circuit.library import QFT',
        '同じ初期コードからのDでは，説明コメントやQFT呼び出しの引数を変更したが，読み込み先はqiskit.circuitのまま残った．判定はround 0から3までimport失敗であった．この事例では，説明内で修正すべき箇所へ言及したことと，実際のコードが変更されたことを区別して確認できる．',
        'Dのみ成功した保存事例は，G4のQPE課題（T8，seed 10）である．初期コードはqc.inverse_qft(...)を呼び出し，保存判定は回路構築失敗であった．Dの1回目の修正ではQFTをqiskit.circuit.libraryから読み込み，inverse=Trueで構成した回路をappendする形へ変更され，L3成功となった．',
        '修正前（Dの初期コードから抜粋）\nqc.inverse_qft(range(n_counting))',
        '修正後（Dのround 1から抜粋）\nfrom qiskit.circuit.library import QFT\niqft = QFT(n_counting, inverse=True)\nqc.append(iqft.to_gate(), range(n_counting))',
        '同じ初期コードからのFも逆QFTを組み立てる形へ変更したが，QFTの読み込み先をqiskit.circuitとしたため，round 1から3はimport失敗となった．Dでもimport以外のコードやコメントが同時に変化している．掲載した抜粋は変更箇所の一部であり，完全なプログラムではない．',
        '2事例は，APIの利用箇所と保存判定の推移を説明するため，同一モデルから選んだ．頻度や代表性を推定する標本ではなく，片側救済全83組の集計を置き換えない．記録キー，各roundのコードhash，判定と由来をcase_studies.jsonに保持した．成功に至った変更と未成功の変更を観察した結果であり，単独の変更や説明指示が成功原因だったとは断定しない．',
    ])
    catalog = next(ps for title, ps in chapters[6][1] if title == '介入カタログの構成と適用範囲')
    catalog.insert(0, '表7.1に，介入カタログに収録したimport失敗，回路構築失敗，出力不一致の3類型の観測率を示す．読込み，回路構築，出力評価という異なる失敗段階を比較するため，この3類型を取り上げる．件数上位3類型という意味ではなく，表6.3の構文誤り68組は出力不一致65組より多い．率は表6.3と同じ類型の初期失敗数を分母とし，F/Dの救済数またはB4の追加成功数を割って算出した．条件間で初期対象を変えていない．')
    catalog.insert(1, 'この一覧は，本研究のモデル・タスク・生成上限と評価条件で観測した比較結果であり，最も高い率の条件を無条件に推奨する規則ではない．F/Dは同じ失敗コードを修正し，B4は課題仕様から独立再生成する．比較条件の違いは5.1節に述べたとおりであり，未知の課題での優劣はこの表から判断できない．全体の追加計算コストは表6.6に示したが，類型別の率と全体のコストを組み合わせて類型別の費用対効果を推定しない．')


def catalog_rows():
    rows = list(csv.DictReader((HERE/'intervention_catalog.csv').open()))
    return [[r['label'],r['initial_failures'],r['F_rate_percent']+'%',
             r['D_rate_percent']+'%',r['B4_rate_percent']+'%'] for r in rows]


def add_prompt_appendix(d, heading, para):
    p = json.loads((HERE/'experiment_prompts.json').read_text())
    d.add_page_break()
    heading(d,'付録C　実験プロンプト',1)
    para(d,'本節には，実験に用いたsystemメッセージ，課題仕様10種，修正条件R/F/Dと予防条件Pの固定文を掲載する．B4の追加生成にはBと同じ課題仕様だけを与え，前回コードや診断は渡さない．元3実験の保存commitで固定文が一致することを照合した．コード・診断が入る部分は明示的なプレースホルダーへ置き換えた．')
    para(d,'掲載内容は保存されたソースから復元したテンプレートであり，個別のネットワーク要求全文を直接記録したものではない．課題仕様を〈課題仕様〉へ，直前の生成コードを〈前回コード〉へ，評価から作る診断文を〈直前の評価から生成した診断〉へ対応させる．実際の診断文はroundごとの評価値と当時の処理に依存し，元実験と部分追試で同一とは限らない．出典commitとファイルhashはenrichment_manifest.jsonに示す．')
    heading(d,'共通systemメッセージ',2)
    para(d,p['system'],indent=False)
    for task in p['tasks']:
        heading(d,'課題仕様 '+task['task_id'],2)
        para(d,task['text'].strip(),indent=False)
    names={'self_refine':'R：自己見直し','execution_feedback':'F：実行結果提示','self_debugging':'D：自己デバッグ'}
    for item in p['repair_templates']:
        heading(d,'修正テンプレート '+names[item['condition']],2)
        para(d,item['text'],indent=False)
    heading(d,'Pの予防的注意事項',2)
    para(d,'Pは課題仕様の後に改行を2個挿入し，次の固定文を追加して1回だけ生成する．B/R/F/Dの初回は課題仕様だけを与える．')
    para(d,p['preventive_appendix'],indent=False)
