# 关联台模块维护入口

- Module key：`reconciliation-workbench`
- 类型：页面模块
- Route：`/`
- Page key：`reconciliation-workbench`

## 修改前必读

- `docs/product-specs/reconciliation-and-workbench.md`
- `docs/modules/reconciliation-workbench/boundary-io.md`
- `docs/modules/workbench-relations/boundary-io.md`
- `docs/modules/canonical-facts/boundary-io.md`
- `docs/modules/batch-accounting/boundary-io.md`
- `docs/modules/permissions-and-audit/boundary-io.md`

## 当前业务边界

关联台是 canonical OA、银行流水、发票、ETC 汇总事实与 active 正式关系的读写工作台。页面只有 `paired` 和 `unpaired` 两个关系区：

- 满足冻结 OA/发票要求的 active relation 进入 `paired`。
- 未满足冻结要求的 active relation 保持同 case 分组进入 `unpaired`，并显示缺失类型。
- 没有 active relation owner 的 canonical fact 作为 singleton 进入 `unpaired`。

页面不拥有自动候选、matching decision 或第三种关系状态。关系来源只进入 provenance/audit，不参与分区；历史 `case_id`、旧 candidate metadata 或 display tag 不能覆盖当前 active relation 状态。

## 当前读取链

```text
ReconciliationWorkbenchPage
  -> /api/workbench、/groups、/groups/detail、/rows/{id}、relation preview
  -> Workbench read routes（鉴权、参数、HTTP 映射）
  -> WorkbenchQueryFacade
  -> PostgresWorkbenchCanonicalQueryRepository
  -> app.oa_applications
     + app.bank_transactions
     + app.invoices
     + app.etc_* canonical snapshots
     + app.workbench_pair_relations(status=active)
  -> 纯 grouping / zone / requirement policy
```

所有页面读端点直接查询 PostgreSQL canonical facts。一个端点内的 rows、summary、facets/counts 使用同一显式 `REPEATABLE READ READ ONLY` snapshot；repository 设置 2 秒 statement timeout，并使用有界分页和批量 hydration。

页面不读取 `read_model.workbench_*`、active generation、Redis generation cache、`read_model_status`、`read_model_version`、`source_versions` 或 refresh queue。`/api/workbench/refresh-status` 与 `/api/workbench/events` 已从页面合同删除；loading、empty 和 error 由普通请求状态表达，不存在 `202 refreshing`、轮询或旧 payload fallback。

## 写入链

```text
preview（canonical snapshot，最多 20 行）
  -> confirm / withdraw mutation
  -> WorkbenchWriteFacade
  -> relation command service + relation UoW
  -> transaction 内重验 canonical identities / row types
  -> transaction 内锁定并重验 active relation ownership / business versions
  -> app.workbench_pair_relations + history + idempotency + audit
  -> mutation 成功后前端重新 GET 当前页面
```

preview 只用于展示和生成 `preview_id`；正式 command 不信任 preview 派生行。写入不接收 `expected_read_model_version`，继续使用 `submit_expected_versions` 等 canonical relation 业务版本、幂等 fingerprint 和 CAS。选择对象消失、类型变化、占用变化或版本冲突返回 `409`。

## 代码入口

- 前端：`web/src/pages/ReconciliationWorkbenchPage.tsx`、`web/src/components/workbench/`
- API client/types：`web/src/features/workbench/`
- Route：`backend/src/fin_ops_platform/app/routes_workbench.py`
- Query service：`backend/src/fin_ops_platform/services/workbench_query_facade.py`
- Query repository：`backend/src/fin_ops_platform/services/postgres_repositories/workbench_canonical_query.py`
- 纯分组/规则：`workbench_relation_grouping.py`、`workbench_sql_projection.py` 中复用的纯 payload policy
- 写入：`workbench_write_facade.py`、`workbench_relation_command_service.py`、`workbench_uow.py`

## 共享 generation 隔离

旧 Workbench active-generation builder、worker、manifest 和表仍可能被 batch-accounting 等其它调用方消费，本模块不删除这些共享资源。它们不得重新接入关联台页面请求热路径；最终共享清理由跨页面主控在所有调用方迁移后统一完成。

## 不变量

- `paired = complete active relation members`。
- `unpaired = incomplete active relation members + unowned canonical facts`。
- 两区不相交且完整覆盖当前 scope 内可见 canonical facts。
- 一个 canonical member 最多属于一个 active relation。
- ETC collapsed group 只使用已提交/关闭且有 canonical invoice/link 证据的 owner，优先级为 active link > business batch > submission fallback。
- 未知 zone、非法分页/筛选、重复 identity、缺失 active member、类型漂移或跨 case 占用冲突均 fail closed。

## 维护文档

- `boundary-io.md`：直接/上下游 I/O、事务、性能和共享 HANDOFF。
- `state-machine.md`：页面、preview 和正式关系状态。
- `tests.md`：七类测试、查询次数 guard 和验证命令。
- `implementation-notes.md`：历史实施记录，不是当前运行时合同。
