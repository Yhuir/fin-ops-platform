---
phase: 19-audit-readiness
plan: 19
status: complete
completed_at: 2026-07-11
requirements:
  - AUDIT-01
  - AUDIT-03
  - AUDIT-05
  - AUDIT-06
  - AUDIT-07
  - AUDIT-09
  - AUDIT-10
---

# 19-19 执行摘要：完整测试基线归零与运行时任务所有权闭环

## 结果

本计划已完成。13 个已分类 backend failures 已全部收敛，完整 backend 为 **4389 passed / 42 skipped / 589 subtests passed，0 failure**。修复遵守现有模块边界：12 项 stale contract/fixture/guard 回到当前正式事实，legacy bank exception 的真实幂等缺陷在 adapter/facade 内收口；没有恢复 candidate fallback、并行 case owner、旧付款状态或宽松 freshness gate。

全量顺序验证还发现一个此前被单测顺序掩盖的生产竞态：OA reset 在后台任务执行中 reload runtime 会替换 `BackgroundJobService`，导致两个 owner 双写同一 store、查询瞬时 404，并可能误标 interrupted。当前进程内 reload 现在复用同一 owner，首次启动/真正重启仍创建 owner并执行恢复，职责与 I/O 保持单一。

## 关键变更

- Workbench all-scope version断言改为 composed active month shards；input-invoice direct-fresh allowlist 精确指向两个 current fresh-gate owner。
- OA evidence、deterministic mock 和 Browser 回归删除旧 `支付少了` 运行时状态；candidate relation 明确保持 `未支付`，只有 active relation 才能变为 `已支付`。
- 成本统计 fixture 经正式 confirm-link 建立 active relation；candidate-only 不计成本；全银行支出从 canonical bank facts 独立投影。
- permissions inventory 登记 cost-statistics tag-rules PUT、保存控件和 dynamic opener，read-export 下保存 disabled 且 mutation 为零。
- OA reset 保留普通 canonical invoice，并从 attachment cache 重建 OA attachment；测试按 identity 证明，不依赖行顺序或 OCR fallback。
- legacy bank exception 仅在 exact legacy identity/row-set/month/code/manual-review case 下复用 scenario 并幂等 replay；其它冲突 fail closed。
- runtime reload 不再替换 process-owned background-job service；删除双 owner/双写窗口，没有增加兼容分支。

## 验证

- 完整 backend：**4389 passed / 42 skipped / 589 subtests passed**。
- 目标 backend contract set：**162 passed / 17 subtests passed**。
- 完整 frontend：**71 files / 833 tests passed**；成本统计定向 **24 passed**。
- Chromium permissions role matrix：**7 passed**；candidate relation semantics：**2 passed**。
- production frontend build：passed；仅有既有 HeroUI CSS/minified chunk warnings。
- `bash scripts/verify.sh lint`、`bash scripts/verify.sh docs`、`git diff --check`：passed。
- 旧合同扫描：运行时/Browser fixture 不再含 `支付少了`；剩余两处仅为“已移除”文档与负向 `assertNotIn`。旧 aggregate version、成本 fixture mutation helper、cost-statistics static permission 分类均无残留。

## 七类测试责任

| 类别 | 覆盖 |
|---|---|
| Business core | active relation 才进入成本、candidate unpaid、legacy exception exact replay/异码 conflict、OA reset canonical invoice preservation |
| Service | cost projection lineage、reset/reload owner continuity、exception application idempotency、fresh gate ownership |
| API contract | confirm-link fixture、cost tag-rules permission、reset job stable query envelope、all-scope schema version |
| Read model/cache/job | canonical bank-flow projection、OA reset read-model rebuild、background-job owner跨 reload、freshness owner guard |
| Frontend | cost tag-rule drawer、OA 二态展示、read-export disabled save、全量 833 regressions |
| E2E integration | permissions Chromium、candidate relation negative semantics、reset→reload→job completion、active relation→cost read model |
| Existing regression | 完整 backend/frontend/build、architecture/docs/inventory guards、旧状态/旧 owner/旧 helper扫描 |

## 明确未闭环

- App 内部 17 页 v17 System Audit 的本地合同和测试现已零失败，但它仍只证明一个 immutable PostgreSQL snapshot 中“已登记的 App 内部合同”。
- 外部银行/OA/发票/ETC control evidence 尚未版本化登记/采集，因此 `external=unknown`、`end_to_end_source_truth=unproven` 仍是唯一正确结论。
- 未连接或写入生产；未部署、refresh、repair、drain queue 或修改生产数据。生产只读执行仍需用户明确授权。
