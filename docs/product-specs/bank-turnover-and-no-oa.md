# 银行明细、往来款与免 OA 流水

本文维护银行明细、流水标签、往来款管理和免 OA 流水批处理的当前业务口径。

## 银行明细

银行明细页面展示银行原始字段、系统标签、关系状态和跨页面刷新结果：

- 原始银行字段必须保留可追溯性。
- 标签结果来自统一分类/策略，不由页面临时判定。
- 列表状态要反映 read model freshness。
- 关联台、待找发票、往来款和成本统计会消费银行明细事实。

## 流水标签和分类

标签规则应集中维护：

- 标签输入：银行原始字段、金额方向、交易对手、摘要、项目、已有关系。
- 标签输出：业务类型、自动匹配输入、异常原因、置信度或规则来源。
- 规则变更后需要触发受影响月份/对象的刷新。

## 往来款管理

往来款管理关注外部对象关系、候选识别、人工闭环、利息和关联台同步：

- 往来对象 identity/dedup 不应散落在页面。
- 状态分类应由统一 turnover classification/state policy 维护。
- 利息、项目归因和对象关系需要可审计。
- 自动识别只产生候选和差额提示。`deterministic` 表示系统发现同组零差额候选，不表示业务已闭环。
- 页面汇总行只承载组级聚合、余额和展开入口；流水选择、补充信息编辑、确认闭环和撤销归并等写操作必须以真实流水行为入口。
- 所有外部往来闭环都必须由用户在外部往来款管理页手动选择同一往来组内真实流水确认；可选择多笔流水，但必须同时包含收入和支出，且收支合计差额为 `0.00`。确认前不进入关联台已配对区。
- 人工闭环成功后，后端在同一写事务中写 Turnover 手动闭环 evidence 和 Workbench active pair relation。Workbench relation 是外部往来闭环的共同事实源；若所选流水已存在仅含 OA + 银行的 active relation，确认闭环应把这些既有关联合并进同一个 `turnover_manual_closure` active case。确认成功后，外部往来台账必须在对应流水展示“收支闭环”；关联台必须保留同一个 canonical `case:*` relation/evidence。展示分区由 relation metadata 的 OA/发票 requirement 决定：未满足 paired 条件时留在待处理 open 区，满足条件后进入 paired 区，不再把 open relation 称为候选关系状态。
- 已确认的外部往来闭环不能直接追加流水；用户发现漏选流水时，必须先撤回原闭环关系，再重新选择完整流水确认。
- 撤回范围必须受限：当 Workbench active relation 仍是只含 `oa` + `bank` rows 的 `turnover_manual_closure` 时，外部往来款管理页可以撤回；撤回只撤回外部往来闭环关系，并恢复确认闭环前已有的 OA-bank relation。若该 Workbench relation 已在关联台补齐发票或其他业务 row type，外部往来页不得直接撤回整组关系，必须转到关联台撤回完整关系。
- 旧的自动关系和旧 `sync_to_workbench` 字段只能作为历史兼容/候选信息，不作为闭环事实。

## 免 OA 流水

免 OA 流水用于没有 OA 单据但仍需业务处理的流水批次：

- 批量处理必须记录范围、原因、操作者、状态和审计。
- 未提交候选只包含尚未被关联台 active relation 占用的银行流水；已在关联台配对或已由免 OA 批次提交的流水，不应再作为未提交候选重复出现。
- 已被银行明细识别为内部往来的两条银行流水可以从关联台确认入口发起配对，但闭环事实必须归入免 OA 流水批量处理：后端提交内部往来免 OA 批次，并写入 `relation_mode=no_oa_bank_batch`，不得为这类流水直接写普通 `manual_confirmed` 关系。
- 处理结果会影响银行明细、关联台、往来款和成本统计。
- 规则简单且只在单页使用时可保留页面 service；被多页面消费时应进入统一 policy/read boundary。

## 相关文档

- 页面影响：`../app-architecture/pages.md`
- 对象去重：`../operations/object-identity-dedup.md`
- API 契约：`../dev/api-contracts.md`
