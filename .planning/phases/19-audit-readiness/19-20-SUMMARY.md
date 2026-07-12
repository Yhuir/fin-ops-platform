---
phase: 19-audit-readiness
plan: 20
status: complete
completed_at: 2026-07-11
requirements:
  - AUDIT-01
  - AUDIT-02
  - AUDIT-04
  - AUDIT-05
  - AUDIT-06
  - AUDIT-07
  - AUDIT-08
  - AUDIT-09
  - AUDIT-10
---

# 19-20 执行摘要：外部完整快照 exact proof 闭环

## 结果

本计划已完成本地生产能力闭环。银行、OA、普通发票和 ETC 不再由 free-text、count-only、总额或单个文件 hash 推断完整性；四域都有唯一版本化 complete-snapshot manifest 合同，并在 App Health System Audit 的同一 PostgreSQL immutable snapshot 内与 canonical facts 做 exact item set、关键字段 fingerprint 和 controls 双向 equality。

内部 17 页通过与外部来源证明保持独立。缺 evidence 为 `unknown/unproven`；latest revoked、expired、coverage/contract 非法或任一 missing/extra/duplicate/field/control mismatch 为 `fail/unproven`；只有四域全部精确通过才返回 `proven_as_of_external_evidence`，且声明绑定 evidence observed/source snapshot 与当前 system snapshot。

## 架构与 I/O

- 纯合同/normalize owner：`ExternalControlEvidenceService`。
- 持久化 owner：`PostgresExternalControlEvidenceRepository`，immutable append + audited revoke。
- 只读证明 owner：`audit_external_control_evidence`，只接受 caller-owned transaction。
- 运维入口：`external_control_evidence` CLI；validate/dry-run 不连接数据库，apply 要求 actor/reason。
- 数据库权限：API/worker/readonly role 只读 evidence；写入仅受控 migrator/operator role。
- System Audit/HTTP/UI 无采集、登记、撤销、refresh 或 repair 能力；没有外部网络 I/O 污染 read-only Audit。
- 17 页 external dependency 由 registry 显式 keys 决定；旧 `_external_evidence(registrations)` 说明文字分类器删除并由 source guard 禁止回流。

## 旧链路删除

- 删除旧 free-text external classifier；不保留并行 fallback。
- mock/runtime 不再用“存在说明文字”等价 evidence registered。
- 未新增 HTTP/UI 写入口、App self-generated manifest、count/hash fallback 或 latest-revoked 回退。

## 验证

- disposable PostgreSQL 0001–0099：**3 passed**，覆盖四域 exact pass、field drift、canonical omission、latest revoke 与 System Audit integration；临时数据库已删除。
- 目标 backend：**124 passed / 3 skipped / 17 subtests passed**。
- 完整 backend：**4407 passed / 44 skipped / 589 subtests passed**。
- 完整 frontend：第二轮 **71 files / 834 tests passed**；定向 App Health **7 passed**。
- Chromium App Health：**4 passed**。
- production frontend build：passed；仅有既有 HeroUI CSS/chunk warnings。
- `bash scripts/verify.sh lint`、`bash scripts/verify.sh docs`、`git diff --check`：passed。
- frontend 首轮全量有一个 Workbench withdraw 时序断言失败；同一用例精确重跑与第二轮全量均通过，未修改该非相关业务链隐藏问题。

## 七类测试责任

| 类别 | 覆盖 |
|---|---|
| Business core | manifest contract、normalize、identity/fingerprint/control、partial/duplicate/invalid fail-closed |
| Service | immutable register/revoke、幂等、audit event、四域 exact comparer、single-snapshot orchestration |
| API contract | v18 System Audit external schema、unknown/fail/pass 和 bounded claim；无新写 API |
| Read model/cache/job | existing 17-page freshness/queue/current-effective full regression；external comparer 不写 read model/queue |
| Frontend | external domain status/as-of、unknown/fail/pass tone、旧结果清除、全量 834 regressions |
| E2E integration | full migrations → register manifests → exact proof → System Audit → Chromium UI |
| Existing regression | 完整 backend/frontend/build/lint/docs/diff、legacy classifier/source guard、migration grants |

## Grill 后续门禁

本地代码能力完成不等于生产来源完整性已证明。仓库中没有独立采集的真实四域 artifact/manifest，本轮也没有明确授权生产部署或写入 evidence audit facts。因此下一计划已生成但处于 gated：必须先取得四域独立输入和生产部署/evidence-write 明确授权，再部署 0099、离线 validate/dry-run、受控登记、运行只读 System Audit 并保存结构化报告。任何 mismatch 先分类，禁止根据旧样本直接 refresh/repair/write 生产数据。
