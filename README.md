# jma_navigator（気象庁ナビ）

気象庁HPで「知りたい情報」へたどり着くための案内アシスタント。
質問（日本語）→ 該当ページのURLを地域・地点まで指定して案内する。「となりの孫」の画面ガイド方式を参考に、**ディープリンク中心のハイブリッド方式**で作る。

詳しくは [jma-navigator.md](jma-navigator.md) を参照。

- 開始日: 2026-10-27
- 状態: **一旦中断（2026-10-27）。2026-10-30 に再開手順1〜3を実施（Phase 3: リンク検査）。launchd登録済み（毎週水曜9:30）。Phase 4: ローカルWeb画面あり（`python3 server.py`）**。Phase 0〜2 完了（カタログ21項目・評価2版・LLM版）。再開手順は [jma-navigator.md](jma-navigator.md) 末尾「一旦中断時点のまとめ」
- 参考: `~/projects/tonari_no_mago`（Chrome拡張＋プロキシ＋評価セット方式）
- 公開版（Render・URLを知っている人向け・検索には載せない）: **https://jma-navigator.onrender.com**（2026-10-30 公開。無料プランのため初回は起動待ちで数十秒かかることがある。手順・設計は [jma-navigator.md](jma-navigator.md) §21）。個人運営の非公式サービス
