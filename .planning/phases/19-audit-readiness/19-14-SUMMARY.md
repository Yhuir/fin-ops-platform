---
phase: 19-audit-readiness
plan: 14
status: complete
completed_at: 2026-07-11
requirements:
  - AUDIT-01
  - AUDIT-02
  - AUDIT-03
  - AUDIT-05
  - AUDIT-06
  - AUDIT-09
  - AUDIT-10
---

# 19-14 执行摘要：Settings direct-canonical、credential 安全摘要与 reset queue 证明

## 结果

本计划已完成。`settings` 已从 unavailable 升为 ready。统一 Audit 在一个 `REPEATABLE READ READ ONLY` PostgreSQL snapshot 内证明唯一 settings singleton、正式结构与归一化配置、非敏感 OA applicant credential registration，以及 settings data-reset durable job 状态；本页没有 manifest read model，也不消费 pairing relation，因此没有伪造下游 consumer 或关系证明。

## 关键变更

- 新增唯一 `settings_page_audit` repository proof owner；registry、operations repository 与设置页统一 Audit 控件只按 page key dispatch，不新增 refresh、provider、reset 或写入口。
- registry 的 `settings.read_model_keys=()`、`relation_proof_required=false`，proof revision 升至 `page-audit-contract.v13`，ready/unavailable 变为 13/4。
- 直接从 `app.app_settings(settings_key=app_settings)` 验证 singleton、formal/raw payload、固定点 normalization、配置 family、集合/引用/版本与控制 fingerprints；不把 Workbench/tax/cost/search 等写后影响目标冒充本页 consumer。
- credential proof 只读取 applicant identity、enabled/status、version/time 与 `has_credential` 布尔值；SQL、report、issue samples 和测试均不选择、解密、返回或 fingerprint ciphertext/password/token。
- `job.background_jobs(job_type=settings_data_reset)` 的 active 状态阻断 freshness/queue，未确认 terminal failure 阻断 integrity；Audit 不创建、取消、重试、ack 或执行 reset。
- 真实旧链路扫描发现 Turnover Ledger 本地 tag-selection UoW 仍直接保存 settings store 并 `getattr/setattr` 私有 `_snapshot`。现已改为 `AppSettingsService` 领域化 state/commit/restore 端口，queue 失败只回滚 tag-selection family；删除 server `_refresh_local_app_settings_snapshot(...)`、整份 snapshot save/refresh 与私有字段访问，并增加 runtime guard。
- PostgreSQL tag-selection UoW 仍通过 supplied transaction 写 canonical settings/audit/outbox；这是正式事务 I/O，不是 fallback，未被错误移除。
- 外部 OA/project provider、credential 实际登录、真实 reset 后多页 smoke 和生产 worker drain 明确属于后续 external/production gate。

## 验证

- Settings Audit、registry、operations、App Health、credential、reset 与 runtime boundary 目标集：**492 passed / 1 known baseline failure / 38 subtests passed**；唯一失败为既有 reset fixture 多出 `iv-o-202604-001`，不是本计划新增失败。
- Turnover Ledger API 边界与回滚：**144 passed / 28 subtests passed**；新增领域端口单测和 runtime guard 均通过。
- 完整 frontend：**71 files / 831 tests passed**；production build passed。既有 HeroUI CSS/chunk warnings 未由本计划引入。
- lint、docs、`git diff --check`：passed。
- disposable PostgreSQL 应用正式 migrations `0001..0096` 后：
  - clean fixed-point settings + disposable credential 得到 `integrity=pass / freshness=fresh / queue=drained`，且 `database_snapshot=true`；
  - report 不包含 disposable password；
  - duplicate/non-normalized access control payload 返回 `settings_payload_not_normalized`；
  - active reset job 返回 `freshness=not_fresh / queue=backlog`；
  - 恢复后重新 pass，临时数据库已删除，未连接生产、未执行 reset 或 enqueue refresh。
- 完整 backend baseline：**4355 passed / 13 failed / 37 skipped / 589 subtests passed**。13 项与进入本计划前相同类别：Workbench builder expectation、7 个旧 cost-statistics fixtures、OA deterministic marker、permissions inventory、fresh-status guard、settings reset fixture、Workbench duplicate behavior；Settings Audit、credential 安全、Turnover Settings 边界无新增失败。

## 七类测试责任

| 类别 | 覆盖 |
|---|---|
| 业务核心 | settings fixed-point normalization、singleton/version、配置集合/引用、secret-like key 检测 |
| Service | AppSettingsService domain commit/rollback、credential metadata、reset service 既有链路 |
| API contract | v13、ready/zero-read-model/relation non-consumer、admin-only、secret-safe response |
| Read model/queue | direct canonical 无伪 read model；active/terminal reset job gate |
| Frontend | Settings 管理员统一 Audit 控件；71/831 全回归和 production build |
| E2E | 全迁移 PostgreSQL clean、non-normalized payload、secret-safe credential、active queue 反证 |
| Regression | Turnover local queue failure rollback、跨模块私有 snapshot guard、全部既有失败面不扩大 |

## 明确未闭环

- 四个页面仍为 `unavailable`：App Health operations、银行流水导入、发票导入、ETC 发票导入。
- system-level consistency snapshot/version set、外部银行/OA/发票/ETC control evidence、13 个 backend baseline failures 和授权生产闭环仍未完成。
- 本次证明“已登记 App 内部 Settings 控制事实”完整一致；不能证明外部 OA 项目没有漏同步、credential 一定可登录或真实 reset 已安全完成。
