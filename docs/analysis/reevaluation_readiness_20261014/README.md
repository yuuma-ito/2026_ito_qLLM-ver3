# 5,000件再評価のNO-GO条件への対応

2026-10-14。前提は[文献監査](../literature_reliability_20261014/README.md)、[原文と実装の再点検](../literature_reliability_20261014/source_implementation_recheck/README.md)、[評価方法点検](../evaluation_methods_20261014/README.md)。前報の記録・取得証拠・CSVは保持した。今回の結果は別フォルダに保存し、旧判定・raw.jsonl・固定発表スナップショットを上書きしない。

**判定：CONDITIONAL GO。** 下記の隔離・checkpoint・補助検査を備えた保存コードの再採点について、限定的な試験を行う準備条件を解消した。ただし、全件用の実行計画・資源制限の妥当性・補助検査の適用範囲を確定してから、本番実行の別指示を受ける必要がある。今回のCLIは最大12記録・48 roundに制限し、5,000件を実行する選択肢を持たない。本番5,000件は開始していない。

## 主判定と補助判定

主判定は **evaluation_policy_v4** を保持する。距離0.05、TVD、8192 shots、simulator/transpiler seed 42、構造条件、ユニタリ回路からの純粋状態取得を変更しない。`harness/evaluator.py:evaluate_circuit`への切り出しは、生成コードの構築後に行っていた同じ処理を、新しい評価プロセスでも呼び出すための変更である。従来の`evaluate`はその関数へ委譲する。全10タスクの既知正解を、直接実行と隔離・QPY往復で比較するテストを追加した。

新しい **coherent_oracles_v1** は別の`auxiliary`列へ保存する。補助不合格によってL2/L3を書き換えない。`not_applicable`、`not_implemented`、`diagnostic_only`も成功には数えない。隔離が拒否した操作や時間・資源不足は主判定の誤答に変換せず、`runtime_status`で区別する。ソースhash・ライブラリ版・資源条件が同じcheckpointだけを再開できるため、同じ主判定version名でも実装変更は混在できない。

旧記録との比較は同一コード・task・round単位で行う。旧フィードバックで選ばれた保存済み履歴を再採点するだけで、新しいフィードバックによる修正実験の結果ではない。初成功、途中の成功、最終成功、成功後の退行を別に保存し、存在しない後続roundを補わない。

## 修正と失敗の再現・検証

テストは[tests/test_reevaluation_readiness.py](../../../tests/test_reevaluation_readiness.py)。旧版に存在しなかった機能について、「旧テストを実行して失敗した」とは記載しない。代わりに欠落していた条件と、新機能へ故障を注入した検査を対応付ける。

| 対応 | 失敗の再現・故障注入 | 修正後の検証テスト | 実装 |
| --- | --- | --- | --- |
| QFT/IQFTの列位相 | `DFT @ diag(1,1,-1,1,…)`は旧8基底＋0/1の2重ね合わせに全て忠実度1。0/2の重ね合わせでは0 | `test_old_qft_blind_spot_and_new_anchor_coherences`：順・逆変換で22入力が反例を検出し、全体位相だけの正解は通る。process fidelityは手計算の0.5625に一致 | `harness/supplementary.py:coherent_operator_check` |
| 生成回路の変換補助 | 固定入力の出力を維持した別ユニタリが主L3を通る | `test_whole_preparation_qft_reference_agrees_and_detects_mutation`：既知正解は主・補助とも成功、反例は主成功・補助不合格 | `fourier_reference`, `auxiliary_checks` |
| 閾値 | 0.9975と厳密な換算値の間では、旧試行忠実度の検出条件と主距離判定が食い違う | `test_exact_fidelity_threshold_detects_rounded_gap_and_boundary`：換算・厳密不等号・norm違反・非ユニタリ拒否を確認 | `fidelity_cutoff`, `pure_fidelity` |
| 状態補助 | Bell/GHZへZを加えてもZ基底分布は同じ。部分reset後のensembleを純粋状態として換算できない | `test_independent_bell_ghz_phase_and_reset_oracles`：正解、相対位相の不正解、手計算の純度1/2・忠実度1/4を照合 | `auxiliary_checks` |
| ホストからの隔離 | 既存の同一プロセス評価では、無害な外部fixtureのファイル読み取りを含むBellコードが成功する | `test_policy_denial_is_not_model_wrong_output`：新経路ではpolicy_denied。`test_sandbox_refuses_host_files_network_processes_and_secret_environment`で外部読み書き、任意scratchファイル、通信、fork/exec、外部signal、環境変数の非継承を確認 | `harness/sandbox_policy.py:install`, `harness/isolated_evaluation.py:_stage` |
| 評価関数の汚染 | builderから成功JSONを直接書く／評価関数をmonkeypatchする | `test_builder_cannot_inject_oracle_success`：protocol_error。`test_monkeypatched_builder_does_not_change_fresh_oracle`：独立プロセスは本来の不正解を検出 | `isolated_evaluate`, `harness/isolated_worker.py:main` |
| 資源・異常終了 | sleep、CPU無限ループ、3 GiB割当、exit(7)、存在しないmoduleのimport | `test_wall_cpu_memory_crash_and_import_errors_are_separate`：wall_timeout、cpu_limit、memory_limit、worker_crash、モデルimport_errorを区別 | `_stage`, `install`, worker |
| 途中停止・重複 | claim後の中断、同一完了keyの再申請、完了結果の変更 | `test_checkpoint_restart_duplicate_and_result_immutability`, `test_checkpoint_hard_exit_releases_lock_and_resumes_pending`：os._exit(19)後も完了行は再実行せず、未完claimだけ回復 | `harness/reevaluation_checkpoint.py:Checkpoint` |
| 破損・版混在・競合 | 結果JSONだけ改変、壊れたSQLite、別profile/source/scope、同時writer、重複case | `test_checkpoint_corrupt_results_and_database_are_refused`, `test_checkpoint_version_source_scope_mismatch_and_lock`：いずれも拒否。自動修復・旧結果上書きなし | `Checkpoint.__enter__`, `claim`, `finish` |
| 全履歴相当の規模 | 9,517個の合成key。コード実行はゼロ | `test_checkpoint_accepts_full_history_sized_catalog_without_execution`：先頭・末尾の記録保存／再開、予定件数を確認。全件実行性能の検証ではない | `Checkpoint` |
| 統合・公開保存 | 合成の保存コード→隔離→checkpoint→再開。公開ファイルの重複作成 | `test_synthetic_pipeline_isolation_checkpoint_and_zero_execution_resume`：初回1件、再開0実行。元raw不変。`test_public_report_atomic_publish_cannot_overwrite`：既存公開結果を保持 | `scripts/pilot_reevaluation.py:run_pilot`, `immutable_report` |
| 未対応環境 | Linux以外／隔離初期化失敗 | `test_sandbox_installation_failure_has_no_subprocess_fallback`：通常subprocessへ降格せず停止 | `install`, `isolated_evaluate` |

開発途中には、書き込みを5ファイルへ限定した後の全体テストで16件が失敗した。原因はdillが`tempfile.gettempdir()`で任意ファイルの作成を試み、QiskitのimportがFileNotFoundErrorになったこと。workerが隔離前に指定パスをcacheする修正を実施した。任意ファイル作成の許可は戻していない。この失敗を生成モデルの不具合と扱わない。

## 忠実度0.9975と距離0.05

正規化された純粋状態`a,b`について、全体位相を最適に合わせたユークリッド距離をdとすると、

```
r = |a† b|,  F = r²
d² = ||exp(iφ)a − b||² = 2 − 2r = 2 − 2√F
d < δ  ⇔  F > (1 − δ²/2)²       (0 < δ ≤ √2)
δ = 0.05  ⇒  F > 0.9975015625
```

0.9975は前監査のmutation試行に用いた独自の近似値であり、指定論文の推奨値でも、厳密な主判定換算でもない。新補助はtaskの距離閾値から上式を計算して**厳密な`>`**で判定する。主判定の`d < δ`を維持し、境界を成功に含めない。浮動小数点の境界近傍では丸めの影響が残る。norm/unitarityの検証誤差1e-10、純度を純粋と扱う誤差1e-10も本実装の独自値である。

この換算は**正規化純粋状態同士に限る**。TVD、混合状態、密度行列のFrobenius距離、process fidelity、任意チャネルの最悪入力距離へ適用しない。Bell/GHZで部分resetなどにより混合状態になった場合は`〈ψ|ρ|ψ〉`と`tr(ρ²)`を診断として保存し、主純粋状態の閾値判定には転用しない。主statevector評価が非ユニタリを拒否する方針も維持する。

## QFT補助の適用条件と限界

独立なNumPyのDFT式で期待変換を作り、Qiskitのmockから期待値を生成しない。生成コードの最初のXを自動で除去せず、**回路全体を「X(q0)の入力準備＋3量子ビットの順／逆DFT」という別の補助仕様**と比較する。基底8個と、`(|0〉+|j〉)/√2`・`(|0〉+i|j〉)/√2`（j=1…7）の14個、計22入力を使う。

ユニタリ同士が全基底で忠実度1なら、各列は期待値と位相だけ異なる。基底0と全列を結ぶ重ね合わせでも忠実度1なら、列位相は共通となる。これは**厳密一致の場合の性質**であり、有限閾値での22件成功からdiamond normや全入力の最悪誤差を保証しない。process fidelity `|tr(V†U)/8|²`も診断値で、主判定へ使わない。

固定入力001の正しい出力だけを準備する回路、入力依存の全体位相を持つ別変換、初期化・resetを使う回路は、このユニタリ変換補助を満たさない場合がある。固定出力benchmarkとしての主成功とは別の意味である。Bell/GHZのdensity補助は未測定の正しい幅の回路に限定し、terminal measurementを勝手に削除しない。DJ、BV、Grover、QPE、Ansatzの独立補助は今回の新モジュールでは未実装と明示する。

## 本番対象コードを実行する境界

1. 新規builderプロセスで隔離を設定してからコードを実行し、回路をQPYへ保存する。
2. 親プロセスはサイズ制限付きのbytesだけを複製し、QPYを解析しない。
3. 新規oracleプロセスも隔離してからQPYを読み、信頼済みの主評価と補助評価を行う。builderのPython状態・monkeypatch・namespaceを引き継がない。

Linux x86_64でLandlock ABI≥3とlibseccompが必須。実測ABIは4。stdlib段階の1 threadだけでpolicyを設定し、その後Qiskit/NumPyを読み込む。ABI4では既存threadにLandlockが一括適用されないため、この順序を検査する。通信・fork/exec・別プロセスへのsignal/ptrace/pidfd/prlimit等をseccompで拒否し、将来のpthreadは制限を継承する。環境変数をallowlistから作り直し、APIキー・親のHOME・その他の秘密情報を継承しない。

ファイル読み取りは実行に必要なライブラリ、copyしたharness/tasks、少数のシステムファイルに限定する。親のrepository、raw、.env、home全体は許可しない。書き込みは事前に作成した5ファイルと/dev/nullだけを許可する。各段階は壁時計25秒、CPU soft 15秒／hard 16秒、仮想アドレス空間2 GiB、各出力4 MiB、FD 64、core dump 0。回路は8 qubits・64 classical bits・10,000操作以下、コード1 MiB以下。**これらは論文指定の値ではなく本プロジェクトの独自上限**。親が壁時計超過でprocess groupをkillし、終了時にも残存process groupを除去する。

`RLIMIT_AS`はRSS/cgroup制限とは異なる。5出力ファイルへの限定と各4 MiB上限により任意ファイルを増やすdisk消費を抑えるが、VM・gVisorと同等の境界だとは主張しない。許可済みネイティブライブラリ・kernelの未知の脆弱性、QPY readerの不具合を排除する証明ではない。QPYも非信頼入力として時間・資源制限の内側で読む。

## 専用checkpoint

`Checkpoint`は条件記録とroundを識別する一意key、code SHA-256、原出典と設定hash、task/evaluator/補助/policy/runnerのソースhash、ライブラリ版・sampling・資源条件を固定する。SQLiteのprimary key、`synchronous=FULL`とtransaction、結果JSONのSHA-256、`integrity_check`、単一writerのflockを使う。完了行の変更・重複、破損、別scope/profile/sourceによる再開を拒否する。

claimだけが残る中断は、旧writerのlockが解放された後で未完claimを削除して再申請する。完了行は再実行しない。commit直前に中断した計算は再実行され得るため、**実際の計算のexactly-onceを主張せず、完了結果の重複保存防止を保証する設計**である。runtime failureも完了保存し、同じcheckpointで勝手に再試行しない。修正・資源変更時は別checkpointが必要。manifest欠損や壊れたDBを自動修復しない。SQLite作成途中の中断でmanifestがない場合も停止し、旧ファイルを保持して新規checkpointを選ぶ。

checkpointは`.cache/reevaluation/`へ置き、公開しない。公開JSONはtemp fileのfsync後にexclusive hardlinkで原子的に作成し、同時writerでも既存結果を置換しない。8記録の試験は各roundを対象にし、B/Fの同一初期コードも別の条件keyとして比較可能に保存する。重複防止は同一keyに対するものであり、異なる条件の同じcode hashを記録から落とすものではない。

## 文献・仕様との対応

原文の取得証拠、節・PDFページは[前回receipt](../literature_reliability_20261014/source_implementation_recheck/source_receipts.json)を参照する。新たに論文の取得日時を捏造しない。Abreuらは原文未確認のまま、実装根拠から除外する。

| 出典・箇所 | 原文・仕様の確認済み論点 | 今回への適用と独自設計の区別 |
| --- | --- | --- |
| [R1 §4.1 p.8、§4.3 pp.12–13、§7.2 p.27](https://arxiv.org/pdf/2410.00650v1) | 入力空間、距離・同値性、mutationによる検査の整理 | coherent入力と既知変異を使う動機。22入力・anchor構成・閾値は今回の数式に基づく設計で、論文の指定手法ではない |
| [R2 quantum_info: state_fidelity / process_fidelity](https://qiskit.qotlabs.org/docs/api/qiskit/quantum_info) | 状態・チャネル忠実度の定義 | 正規化純粋状態の内積二乗と、純粋状態に対するdensity期待値を独立式で計算。0.9975を根拠として引用しない |
| [R3 §2.3 p.4、§5 pp.9以降](https://discovery.ucl.ac.uk/id/eprint/1471263/1/06963470.pdf) | オラクルの健全性・完全性、部分的な別オラクル | 主と補助の適用範囲を分け、既知ケースで確認しても全ての誤答を検出したとはしない |
| [R5 §2.3 p.4](https://arxiv.org/pdf/2107.03374) | 生成コード実行をgVisor、network制限で隔離する評価環境 | ホスト保護が必要という論点を適用。今回のLandlock＋seccompはgVisor再現ではなく、Linux固有の独自実装 |
| [R6 Algorithm 1 p.3・Eq.4 p.4](https://arxiv.org/pdf/2303.17651v2) | 停止後の最終出力と履歴 | 保存済みfirst/ever/finalを分離。新feedback経路・Self-Refineの忠実再現を検証したとは扱わない |
| [Linux Landlock: Defining and enforcing a security policy、ABI、Good practices](https://docs.kernel.org/userspace-api/landlock.html) | deny-by-defaultの扱う権限、no_new_privs、ABI<8のthread継承条件 | ABI≥3でfail closed、事前thread数の確認、必要pathのみ許可。仕様例のbest effortへ降格しないのは本タスクの方針 |
| [libseccomp seccomp_rule_add: action・比較条件](https://github.com/seccomp/libseccomp/blob/main/doc/man/man3/seccomp_rule_add.3) | syscall ruleとargument条件の設定 | cloneのCLONE_THREAD条件、prlimit64のpid条件と拒否ruleを構成。拒否集合の完全性は一般に証明していない |
| [Python 3.12 resource: setrlimit / RLIMIT_*](https://docs.python.org/3.12/library/resource.html) | CPU、address space、file size等のprocess制限 | 版3.12のAPIに照合した資源上限。採用数値・ハード上限・wall clockは独自条件 |
| [Qiskit qpy: dump/load・binary format](https://qiskit.qotlabs.org/docs/api/qiskit/qpy) | 回路のbinary保存・復元 | installed Qiskit 2.5.2で往復検査。親でpickle/QPYをdeserializeしない。latest全体を2.5.2と同じとは仮定しない |

4段階の整理では、上記文献・仕様は**原文確認済み**、新機能は記載した関数の範囲で**実装確認済み**、DFT・Bell/GHZ・閾値・故障注入は選んだ入力の範囲で**独立検証済み**。Qiskit/QPY/backendの完全な独立性、任意native codeに対する安全性、未実装6タスクの新補助、全件実行の所要時間と資源適合は**未確認**である。

## テストと少数試験

全体テストは**309件成功、失敗・error・skipは0、非推奨警告40件**。今回の単体・統合・隔離テスト30件も成功した。最終全体テストの所要時間は約70秒。最終結果・case名・実装hashは[verification_results.json](verification_results.json)、関数／テストの現在の行番号は[implementation_locations.json](implementation_locations.json)、QPYのinstalled API signature・ソースhashは[installed_execution_spec.json](installed_execution_spec.json)に保存した。全体テスト成功の確認日時は保存コードの試験より前である。

最初の選択は[pilot_selection.json](pilot_selection.json)の8記録・10 round。[試験](pilot_report.json)と[同一checkpointの再開](pilot_resume_report.json)を別ファイルに保存した。ここではQFT/IQFTがbuild_errorで補助まで到達しなかったため、旧成功の別2記録を[pilot_qft_selection.json](pilot_qft_selection.json)で追加し、別checkpointの[QFT試験](pilot_qft_report.json)・[再開](pilot_qft_resume_report.json)に保存した。最初の選択・結果・checkpointを変更していない。

合計は**10記録・12 round、5モデル名・7 task種**。実行基盤の失敗、欠落、重複keyはいずれも0。両checkpointの再開は追加実行0件。モデルのimport_error/build_errorは評価結果として保存し、基盤障害と混同しない。原出典3組のraw・設定hashは試験後も不変だった。詳細は[pilot_comparison.csv](pilot_comparison.csv)と[pilot_sanity.json](pilot_sanity.json)。

| 確認対象 | 旧評価→今回 | 解釈 |
| --- | --- | --- |
| QPE / gemma4 / seed16 / Bのround0、Fのround0・1 | 失敗→主成功。TVD約1→4.44e-16 | 未使用古典ビットを量子ビット順へ復元する既修正v4の効果。今回新しく主判定を変更したものではない |
| 同じF履歴の初成功 | 旧round2→新round0。最終round2は両方成功 | 旧feedbackは誤った初期失敗を見て修正した履歴。新基準で生成した介入による救出とは解釈しない |
| 追加の生成済みQFT/IQFT正解 | 主成功を保持、補助22入力も成功 | 最小忠実度約1、process fidelity約1。任意コードの完全性保証には拡張しない |
| Bell・QFT・IQFT・Ansatzの初回候補4 round | import_error/build_errorを保持 | モデルコードの失敗。CPU・壁時計・memory・policy_denied等の基盤失敗は発生していない |
| 全12 roundの主成功数 | 5→8 | 変化3件は上のQPE。意図的に選んだ検査集合であり母集団の成功率推定ではない |
| 全10記録の最終主成功数 | 5→6 | 途中roundの成功変化3件を最終成功3件の増加と数えない |

2試験の壁時計は合計**約16.03秒**、子プロセスCPUは合計**約15.26秒**。追加LLM要求・token使用・LLM費用は0。5,000件の時間・費用へ単純外挿せず、起動コスト・失敗段階・全履歴を含む対象数の違いを考慮する。旧feedbackで選ばれたround・同一初期共有・task/seed相関を持つため、5,000件を独立二項試行とするWilson区間やpass@kは算出しない。

再現コマンド（既存の公開結果を上書きしないよう、再実行時は別のreport名を指定する）：

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m scripts.pilot_reevaluation \
  --selection docs/analysis/reevaluation_readiness_20261014/pilot_selection.json \
  --checkpoint .cache/reevaluation/readiness_20261014 \
  --report docs/analysis/reevaluation_readiness_20261014/pilot_report.json
```

公開ファイルへ生成コード、生出力、生例外文、環境秘密情報、checkpoint DBは含めない。保存済みの公開結果を保持し、新しい試験には別selection・checkpoint・reportを使う。

## CONDITIONAL GOの条件と残存リスク

- **主v4による保存済みコードの再採点**を目的とし、coherent補助を主成功率へ混ぜない。厳密なアルゴリズム実装成功率への改称・主判定変更には別の仕様と比較が必要。
- 全件の記録・roundを含む実行計画を、固定した3出典から事前生成・検証する。新CLIの上限を解除するだけで本番へ移らない。checkpoint単体の9,517 key検査は本番schedulerの完成を意味しない。
- pilotにないDJ・Groverなどの保存コードの資源適合と、境界例を追加確認する。sandboxのpolicy_deniedや資源不足が出た場合、誤答・成功率の分母へ黙って算入せず停止・分類する。設定変更は新profile/checkpointで行う。
- 新補助はQFT/IQFT・Bell/GHZの限定仕様。他タスクの既存主判定はそのまま使えるが、全アルゴリズムを独立検証したと報告しない。測定、非ユニタリ、固定入力の同等出力の扱いを明記する。
- 数値境界、有限shotとseed依存、粗い構造条件、Qiskit由来の期待値・実行依存、旧feedbackによる選択バイアスは残る。少数の意図的に選んだpilotの成功率から5,000件の統計的精度・モデル優劣・費用を推定しない。
- kernel/native parserの未知の欠陥に対する強い保証が必要なら、別ホスト・VM等を追加した境界で再確認する。今回のLinux policyはその代替証明ではない。

追加生成、学会原稿の成功率表更新、本番5,000件再評価、Git pushは実施しない。
