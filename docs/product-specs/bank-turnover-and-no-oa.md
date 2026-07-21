# 银行明细、流水规则批量处理、往来款与免 OA 流水

本文维护银行明细、流水标签、流水规则批量处理、往来款管理和 legacy 免 OA 流水批处理的当前业务口径。

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
- 人工闭环成功后，后端在同一写事务中写 Turnover 手动闭环 evidence 和 Workbench active pair relation。Workbench relation 是外部往来闭环的共同事实源；若所选流水已存在仅含 OA + 银行的 active relation，确认闭环应把这些既有关联合并进同一个 `turnover_manual_closure` active case。确认成功后，外部往来台账必须在对应流水展示“收支闭环”；关联台必须保留同一个 canonical `case:*` relation/evidence。关联台只按 active relation 成员显示已配对组；没有 active relation 的事实逐条显示在未配对区，不再存在 open/candidate relation 展示状态。
- 已确认的外部往来闭环不能直接追加流水；用户发现漏选流水时，必须先撤回原闭环关系，再重新选择完整流水确认。
- 撤回范围必须受限：当 Workbench active relation 仍是只含 `oa` + `bank` rows 的 `turnover_manual_closure` 时，外部往来款管理页可以撤回；撤回只撤回外部往来闭环关系，并恢复确认闭环前已有的 OA-bank relation。若该 Workbench relation 已在关联台补齐发票或其他业务 row type，外部往来页不得直接撤回整组关系，必须转到关联台撤回完整关系。
- 旧的自动关系和旧 `sync_to_workbench` 字段只能作为历史兼容/候选信息，不作为闭环事实。

## 流水规则批量处理

流水规则批量处理只承接无需 OA、也无需发票即可直接生成批次的银行流水：

- 新未提交批次的唯一资格是标签当前 active，且该标签规则同时满足 `requires_oa=false`、`requires_invoice=false`。任一项为 `true`、规则缺失或标签已归档时，该流水都不进入本页面未提交区，应由关联台、待找发票等需要单据的流程处理。
- 页面未提交 bucket 的主标签、子标签和批次都只展示上述合格标签，不得把银行明细的全部 active 标签与当前页 rows 合并后铺满。标签管理抽屉仍展示全部 active 标签，供用户维护 OA/发票规则。
- 已提交和已撤回历史按提交时冻结的批次、标签和 requirement snapshot 展示，不受当前标签是否 active、当前 OA/发票勾选状态或标签改名影响；规则保存不得追溯改写既有 relation。
- 规则保存发生资格变化时，只重算受影响标签曾出现的未提交月份；同一标签从“需要 OA”改为“需要发票”等资格未变化的语义更新只保存规则，不触发 `bank_flow_rule_batch` 重算。
- 设置版本更新与受影响月份 dirty scope/outbox 必须在同一 PostgreSQL 事务提交；请求返回后页面清空旧选择并立即反馈，后台按月份批量收敛 read model，不让全量历史刷新阻塞保存响应。
- 银行流水导入、导入状态变化、手工分类变化和自动标签规则变化都必须经 owner UoW 或 derived lifecycle 输出 `bank_flow_rule_batch` refresh，保证未来流水使用当前资格规则。
- 性能验收目标：规则保存 API p95 ≤ 300ms、p99 ≤ 1s；当前页面受影响月份 enqueue-to-fresh p95 ≤ 1s、p99 ≤ 3s；全部受影响历史月份 p95 ≤ 5s。月份发现和汇总必须使用固定查询数、集合 SQL 与批量 outbox，禁止逐标签、逐流水或逐月份 I/O。

## 免 OA 流水

免 OA 流水是独立 legacy 域，用于没有 OA 单据但仍需业务处理的历史流水批次；它不是当前 `/bank-flow-rule-batches` 页面或 `bank_flow_rule_batch` read model 的运行时 fallback：

- 批量处理必须记录范围、原因、操作者、状态和审计。
- 未提交候选只包含尚未被关联台 active relation 占用的银行流水；已在关联台配对或已由免 OA 批次提交的流水，不应再作为未提交候选重复出现。
- 已被银行明细识别为内部往来的两条银行流水可以从关联台确认入口发起配对，但闭环事实必须归入免 OA 流水批量处理：后端提交内部往来免 OA 批次，并写入 `relation_mode=no_oa_bank_batch`，不得为这类流水直接写普通 `manual_confirmed` 关系。
- 处理结果会影响银行明细、关联台、往来款和成本统计。
- 规则简单且只在单页使用时可保留页面 service；被多页面消费时应进入统一 policy/read boundary。

## 相关文档

- 页面影响：`../app-architecture/pages.md`
- 对象去重：`../operations/object-identity-dedup.md`
- API 契约：`../dev/api-contracts.md`
