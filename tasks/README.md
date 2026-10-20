# 量子回路タスク（tasks）

実験で使う10種類のタスクを定義する Python パッケージです。各モジュールの `TASK` に、生成指示、量子ビット数、期待分布または状態ベクトル、評価しきい値、構造要件、mock用コードをまとめています。

| ファイル | タスク |
| --- | --- |
| [t1_bell.py](t1_bell.py) | Bell状態 |
| [t2_ghz.py](t2_ghz.py) | GHZ状態 |
| [t3_dj_constant.py](t3_dj_constant.py)・[t3_dj_balanced.py](t3_dj_balanced.py) | Deutsch–Jozsaの定数・均衡オラクル |
| [t4_bv.py](t4_bv.py) | Bernstein–Vazirani |
| [t5_grover.py](t5_grover.py) | Grover探索 |
| [t6_qft.py](t6_qft.py)・[t7_iqft.py](t7_iqft.py) | 量子フーリエ変換・逆変換 |
| [t8_qpe.py](t8_qpe.py) | 量子位相推定 |
| [t9_ansatz.py](t9_ansatz.py) | パラメータ付き回路 |

[__init__.py](__init__.py) に `Task` 型、一覧取得の `all_tasks()`、ID検索の `get_task()`、難度の割当があります。モデルへの共通指示は [prompts](../prompts/README.md)、条件別の追加指示は [interventions/prompts.py](../harness/interventions/prompts.py) にあります。

期待値や構造要件を変更すると評価の意味も変わります。[評価器テスト](../tests/test_evaluator.py) と [評価仕様](../docs/evaluator_readout.md) を合わせて確認してください。
