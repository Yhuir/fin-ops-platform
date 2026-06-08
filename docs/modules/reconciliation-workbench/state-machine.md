# 关联台 状态机


> 修改 `关联台` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。当前没有独立状态机时，在对应小节写明“不适用原因”，不要删除文件。

## 业务状态

- 当前状态：
  - open：OA、银行流水、发票或折叠发票汇总尚未形成完整关系。
  - paired：后端确认关系已经写入 active Workbench pair relation。
  - pending `etc_invoice_summary`：ETC 批次已人工确认 OA 提交，但未来 OA 单据和银行流水尚未进入或尚未匹配。
- 状态事实源：Workbench active generation、active pair relation、OA/银行/发票事实表、ETC 业务批次和提交批次。
- 允许流转：`source_kind=etc_invoice_summary` 可在 open 区作为一条折叠发票汇总行等待普通配对；当 OA、银行流水和该 ETC 汇总三项符合关联台配对规则并确认后，进入 paired 区。
- 禁止流转：ETC 批次人工确认已提交不等于关联台已配对；没有 OA 和银行流水匹配事实时，不得把 ETC 汇总行直接放进 paired 区。

## UI 状态

- loading：按 Workbench 查询和刷新状态展示，不把 ETC 批次状态替代为关联台状态。
- empty：open 区没有可配对对象才显示空态；ETC 汇总行存在时必须作为 open 候选展示。
- error：read model 或配对动作失败时展示关联台业务错误，不展示底层 SQL/projection 字段。
- stale/refreshing：非 fresh 状态不能把空 rows 当作真实无候选；页面应保留刷新/陈旧提示。
- permission disabled/hidden：无确认权限时禁用配对动作，仍可只读查看 open 候选。

## Read Model / Worker 状态

- Workbench projection 需要把已提交 ETC 批次的散票折叠成一条 `source_kind=etc_invoice_summary` 行；金额使用业务批次上报金额，散票作为可展开明细。
- fresh/missing/refreshing/stale/failed/unavailable 由 read model gateway 和 active generation 决定；ETC 汇总行只是 projection 结果，不单独定义 read model 状态。
- refresh 触发来源：导入确认、OA/银行/发票导入、ETC 人工提交确认、配对确认和撤回。
- 失败恢复：重跑 Workbench refresh 或修复 active generation；不得用前端本地合并绕过 projection。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-08 | 已提交 ETC 批次在 open 区投影折叠 `etc_invoice_summary`，等待普通三项配对 | 关联台 open/paired 分区、Workbench projection | `tests.test_etc_backend` |
