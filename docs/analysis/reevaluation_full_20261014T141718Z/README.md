# 保存済みコードの本番再評価

状態：completed。主evaluation_policy_v4、補助coherent_oracles_v2。

全5000記録・9517 round中、5000記録・9517 roundを採点。基盤障害0件、欠落0 round。

採点完了記録の最終L3：旧2457→新2727。旧失敗→新成功270、旧成功→新失敗0。

主判定と状態／変換補助は別列。first/ever/finalと退行を分離した。旧feedbackで選択された保存コードの再採点であり、新feedbackによる介入実験ではない。元raw・設定・固定発表結果を保持した。LLM要求・LLM費用0。独立二項区間・pass@kは算出しない。

未知の主失敗分類12 round、共有初期の判定不一致0組。これらが残る場合は分析上の確認事項として扱う。基盤障害をwrong_outputへ算入しない。
