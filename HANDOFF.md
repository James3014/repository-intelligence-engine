# HANDOFF

更新：2026-10-11 · by Claude · HEAD `997bfc3`
<!-- 規則見 AGENTS.md「Handoff」。上限 150 行；過期內容移到 docs/archive/HANDOFF-YYYY-MM.md。 -->

## ▶ 下一步（只放一件，必須帶 #Issue）
#78 審查並落地 PR #83，把自我取用的 workflow action pin 從 `@v0.1.1` 改為 `@v0.1.4`。依據：標記為 [P1]；它等待的 v0.1.4 tag／release 已於今日發佈（tag 指向 `997bfc3`），PR #83 為 clean、最近更新。

## 進行中
- #78 / PR #83 只改 `uses:` ref（Closes #78）；必要檢查綠，其中一個 `terminal` run 顯示 cancelled，需確認不影響 required check。
- #86 / PR #89 讓 `verify_cloud_bundle` / `verify_repository_intelligence_report` 重新推導 readiness，拒絕 identity 無效或過期的 REVIEW_READY；clean、檢查全綠，待審查。
- #90 v0.1.4 已發佈（commit `997bfc3`、release 已公開），Issue 仍 open，待確認收尾後關單。

## 待確認（沒有 Issue 號）
- 無。

## 卡住 / 注意
- `v0.1.3` 永遠不會成為 tag（名稱被誤建後刪除的 immutable release 佔用）；0.1.3 內容已併入 v0.1.4。
- #64（Nexus Core two-job gate）看起來已由 #65 實作，Issue 仍 open，需核對是否可關。
- #36 是 `[HYBRID_CANARY]` 研究探針，明示不需實作，不可列入工作排程。
- #79、#80（[P2] hash helper 重複、預設 authority pattern 寫死 Nexus 路徑）尚無 PR。
- Claim ceiling 為 advisory：`REVIEW_READY` / `EIA READY` 不授予核准、合併、release 或 dispatch 權限；tag 移動與發佈需明確授權。
