# 银企核销与关联工作台

本文合并维护银企核销、核销单、关联台、异常处理和跨对象关系确认的当前业务口径。

## 业务目标

- 将银行流水、OA 单据、进项/销项发票、ETC 票据和项目成本关系收敛到可审计的核销链路。
- 关联台提供“候选发现、人工确认、撤回、状态刷新、异常处理”的统一操作界面。
- 核销事实必须能被银行明细、待找发票、税金抵扣、成本统计、往来款等页面复用。

## 关联台职责

- 展示待处理对象、候选对象和已确认关系。
- 支持搜索、筛选、三栏工作流、批量确认、撤回和详情查看。
- 消费后端 read model 或 active generation，不在前端重新拼底层事实。
- 展示 freshness、refreshing、stale、job 等状态，不能把旧 read model 伪装为 fresh。

## 核销关系

核销关系是跨页面事实，至少需要记录：

- 关系双方对象类型、对象 id、来源系统和 source version。
- 关系状态、确认/撤回人、确认/撤回时间、原因和审计信息。
- 影响范围，例如月份、项目、流水、发票、OA 单据、业务批次。

## 异常处理

异常必须结构化记录，不能只依赖页面提示：

- case 类型：缺少候选、金额不一致、重复对象、状态冲突、外部数据缺失、read model stale。
- 动作：忽略、重新匹配、人工确认、撤回、repair、backfill。
- 审计：操作者、时间、前后状态、影响对象、失败原因。

## 设计边界

- 业务规则在后端 policy/service 中维护，页面只消费结果。
- 多页面共享且需要回填/新鲜度的结果，使用 read boundary 或 active generation。
- 命令写入、权限校验、版本冲突和审计不做分发 read model。

## 相关文档

- 页面结构：`../app-architecture/pages.md`
- 运行时和 owner：`../app-architecture/runtime-and-ownership.md`
- API 契约：`../dev/api-contracts.md`
- Worker 运维：`../operations/runtime-worker-governance.md`
