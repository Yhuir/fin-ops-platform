---
phase: 05-cost-statistics-improvements
plan: 18
status: passed
completed_at: 2026-07-16
next_state: IMPLEMENTING
deployment_status: DEPLOYMENT_HOLD
---

# 05-18 Summary：成本 Audit exact-set 单语句收敛

## 结果

`PASS`。成本 Audit owner 的 scope row count、missing scope、duplicate identity、canonical expected-set 四个独立数据库往返已合为唯一
`cost_exact_set_proofs` statement。四个 proof 仍各自在 `UNION ALL` 前排序并 `limit`，原 blocking issue code、message、
subject/scope/details、caller-owned repeatable-read read-only snapshot 和 canonical 双向集合证明均保持。

canonical 分支仍完整执行两类 expected-set：

- 从 active Workbench generation/group/member 构造 OA-bank paired cost expected rows，并与结构化 cost rows 双向比较 count、amount 和完整展示字段；
- 从 active `app.bank_transactions` 构造全部收入/支出 bank-flow expected rows，并与 `cost_statistics_bank_flow_rows` 双向比较 identity、month、count 和 amount。

成本 owner 自有 SQL 已从 7 组收敛为设计规定的 4 组：queue/readiness、source-version、exact-set、business-values。包含 active relation、
会真实触发 Workbench group-row proof 的固定本地总查询预算从 26 降到 23。该预算包含仍必须执行的正式 Workbench/Bank Detail dependency
proof，因此没有用删除上游证明换取更低数字。

本轮没有部署、没有访问生产、没有运行生产 migration/rebuild/EXPLAIN/SLO，也没有
branch/stage/commit/push/PR/stash/reset/clean。没有修改共享 Audit、Workbench/Bank Detail proof owner、API、read-model发布/query、worker、前端、
schema/index、连接池或其他页面代码。

## 旧代码删除与反过度设计复审

- 删除成本 owner 的 `_scope_row_count_mismatch_issues`、`_missing_read_model_scope_issues`、
  `_duplicate_read_model_identity_issues`、`_canonical_expected_set_issues` 四个旧 per-query helper。
- 删除其最后调用方消失后的 `_proof_query_issues`；whole-repo 成本文件扫描证明上述定义/调用均为零。共享 page Audit 的同名通用 helper 属于其他页面
  owner，按隔离要求未删除。
- 只增加一个显式 SQL 和一个既有 issue code→message 常量映射；未引入 query builder、proof context/cache、repository adapter、临时表、
  并行连接、feature flag、fallback 或第二 executor。
- 四分支分别 limited；canonical 仍做 full join 双向 equality，没有退化为 count/hash、自证或总 union 后单一 sample limit。

## 测试与验证

新增/更新：

- `tests/test_cost_statistics_page_audit.py::test_exact_set_proofs_use_one_query_and_preserve_each_issue_contract`：覆盖四类 issue contract、四个 marker、
  四个独立 limit、精确参数顺序、唯一 statement 和旧 helper 零残留。
- `test_clean_audit_preserves_contract_and_active_relation_query_budget`：固定 active-relation 总预算为 23，并继续锁定 relation equality 只执行一次、
  无 Workbench generation summary 重复 I/O 和 Audit 零写入。
- 既有结构化 bank-flow、source-version、business-values、caller snapshot、registry/CLI/operations/System 测试继续保护完整证明和唯一 owner。

已执行并通过：

- page/operations/System Audit：`68 tests`，`OK`，`3 skipped`（默认环境门禁的 PostgreSQL 类）；
- 一次性本地 PostgreSQL 0001–0107 migration + 成本专属 Audit integration：`1 test`，`OK`；
- 成本 API、SQL runtime、runtime/lifecycle/projection rules：`90 tests`，`OK`；
- PostgreSQL repository boundaries：`34 passed`；
- 修改 Python 文件 `py_compile`：通过；
- `bash scripts/verify.sh lint`：通过；
- `bash scripts/verify.sh docs`：通过；
- `git diff --check`：通过；
- 测试库 `fin_ops_cost_audit_test_0518` 已删除并确认不存在。

第一次 PostgreSQL test URL 使用 socket shorthand，正式 migration 安全门禁因 URL 缺少显式 host 而在执行 migration 前拒绝；测试库由 trap 清理。
随后改用显式 `localhost` 的同名一次性数据库，完整 migration/Audit 通过并再次清理。该记录不代表产品失败，反而证明数据库安全门禁按合同工作。

## 七类责任

1. Business core unit：适用；四类 exact-set、双向集合、identity/month/count/amount 与独立 bound 已覆盖。
2. Service-layer：适用；单 snapshot、一次 exact-set I/O、23-query budget、只读和死 helper 删除已覆盖。
3. API contract：response shape 未改；page/operations/System envelope、registry/CLI和成本 API 回归通过。
4. Read model/cache/background job：适用；只读 canonical/结构化 rows，不写、不缓存、不 enqueue；发布、worker与cache未改。
5. Frontend component/interaction：不适用；成本页面、Audit icon 和轻量遮罩未修改。
6. End-to-end business flow：适用；page/CLI/operations/System 唯一 owner 本地分派与 disposable PostgreSQL 完整 Audit 通过；真实数据/浏览器留到统一部署后。
7. Existing regression：适用；成本 API/SQL runtime、repository boundary、共享 dependency proof与其他页面零实现 diff均已保护。

## 文档影响

已更新成本统计 README、boundary I/O、tests、implementation notes 与唯一性能/freshness/遮罩设计，记录 cost-owned 四组 SQL 与 23-query 门禁。
业务口径、API、read-model合同、worker、权限、部署和页面状态机均未改变，因此 product spec、app architecture、全局 read-model合同、worker治理和
state machine 无需修改。共享 `.planning/STATE.md` 属于并行 Phase 21 release 主线，本轮未污染其状态。

## 下一状态与剩余风险

`next_state=IMPLEMENTING`，整体 `/goal` 继续 active；部署状态仍为 `DEPLOYMENT_HOLD`。本轮只生成并执行 05-18，不预生成 05-19。

仍未关闭：

- 真实数据 `EXPLAIN (ANALYZE, BUFFERS)`、Audit 各组耗时、生产 `p95 <=5s`、真实 upstream mismatch 修复与连续 pass；
- 历史 `cost_statistics_cache_warmup` job/delegates 只有在统一部署窗口证明 production active job 为零后才能删除；
- 旧 summary/project API、remaining full-view 调用与 mixed cost-tax owner 仍需按真实 caller/access 证据逐项选择独立删除切片，禁止一次性宽重构；
- 页面/导出/worker/连接池 p95/p99、migration/rebuild、跨页面隔离和浏览器轻量遮罩仍待授权后的统一部署验证。

只有用户明确授权“允许统一部署”后，才进入统一部署和生产证据阶段；局部 PASS 不能标记整体 `/goal` 完成。
