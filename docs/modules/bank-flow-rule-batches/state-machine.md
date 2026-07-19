# 流水规则批量处理状态机

> 本文件定义当前流水规则批量处理状态。当前代码已提供 `/bank-flow-rule-batches` / `/api/bank-flow-rule-batches`，并使用独立 `bank_flow_rule_batch` read model key、worker event、operation barrier target、repository port、PostgreSQL 批次/read model 表和 `app_settings.bank_flow_rule_batch_tag_rules` 规则 family。

## 标签规则状态

| 状态 | 事实源 | 语义 | 允许流转 |
| --- | --- | --- | --- |
| `active_tag_defaulted` | bank-details active tag + 缺少本模块规则 | 银行标签存在，但本模块从未保存规则。默认 `requires_oa=true`、`requires_invoice=true`。 | 保存规则后进入 `configured`；银行标签归档后进入 `inactive_tag_ignored`。 |
| `configured` | 本模块规则 family | 已保存明确 OA/发票勾选规则。 | PUT 保存新版本；银行标签归档后进入 `inactive_tag_ignored` 并从 active grid 隐藏。 |
| `inactive_tag_ignored` | bank-details tag inactive/archive | 标签不再可用于新批次；历史批次保留提交时 snapshot。 | 银行标签重新 active 时按 code 复用规则；若无规则则回到 defaulted。 |

规则含义：

- `requires_oa` / `requires_invoice` 是候选校验、新批次审计提示和规则版本事实，不决定关联台分区。
- 新增标签默认两者都为 `true`，避免新批次缺少明确业务提示。
- 规则保存不追溯改写既有 relation；既有 relation 保留提交时 snapshot。
- 相同规则保存是 no-op，不递增版本、不写 audit、不触发 refresh。

## 批量提交状态

| 状态 | 事实源 | 语义 | 允许流转 |
| --- | --- | --- | --- |
| `candidate` | `bank_flow_rule_batch` read model | 当前筛选下可选择的未占用银行流水候选。 | 用户选择后进入 `selected_draft`。 |
| `selected_draft` | 页面本地状态 | 用户本次选择的银行流水，尚未写事实。 | 提交成功进入 `submitted`; 清空选择回到 `candidate`。 |
| `submitted` | `app.bank_flow_rule_batches` + active relation | 已通过 command service 创建 relation。 | owner withdraw 或 reset-submitted 后进入 `withdrawn`。 |
| `withdrawn` | batch event + cancelled/withdrawn relation | 批次关系已撤回，银行流水释放，可重新按新规则进入候选。 | 不自动恢复为 submitted；重新提交创建新 request/case。 |
| `blocked` | service validation | 重复 row、跨月、跨账户、标签混用、relation 占用、版本冲突、无权限或 read/write safety 不满足。 | 修复输入或刷新后重新提交。 |

提交规则：

- `transaction_ids` 必填且去重。
- 实现初期建议要求同月、同账户、同有效标签 code。若后续允许跨账户或跨标签，必须重新定义 grouping、metadata 和关联台折叠语义。
- 提交时必须冻结每条银行流水的标签 snapshot、规则版本和规则值；银行明细后续改标签只影响新候选，不重写已提交批次。
- 已被 active relation 占用的 row 不得再次提交。
- 提交成功写 `relation_mode=bank_flow_rule_batch`，不是 `no_oa_bank_batch`。
- `POST /api/bank-flow-rule-batches/reset-submitted` 可批量撤回所有当前 submitted 批次；它通过既有 withdraw + relation command 取消 active relation，旧批次进 withdrawn history，银行 rows 在下一次 read model rebuild 后按当前规则重新出现在 candidate/未提交。
- 禁止用手写 SQL 直接把 submitted 改成 draft；必须保留撤回审计、relation history 和 dirty scope。

## 关联台展示状态

| 状态 | 判定 | 语义 |
| --- | --- | --- |
| `unpaired` | canonical fact 没有 active formal relation | 以 singleton 留在未配对区。 |
| `paired` | canonical fact 属于 active formal relation | active relation 的完整成员进入已配对区，不按 requirement metadata 二次分类。 |
| `collapsed` | relation 内银行流水数 `>3` | 关联台默认折叠为摘要行，原始银行 rows 保存在 `collapsed_rows.bank`。 |
| `expanded` | 银行流水数 `<=3` 或用户展开 | 展示原始银行 rows。 |

禁止流转：

- 禁止根据当前规则把 active relation 的成员重新移回 unpaired。
- 禁止规则保存扫描、升级或改写 Workbench/turnover relation。
- 禁止前端根据勾选本地推断 paired/unpaired；必须消费 formal relation/read model payload。

## UI 状态

| UI 状态 | 语义 |
| --- | --- |
| `loading` | 初次加载标签规则或批次列表。 |
| `refreshing` / `stale` | read model 非 fresh；页面可展示旧数据但必须提示刷新中/陈旧，不能把空态当真实结果。 |
| `editing_rules` | 抽屉打开，左侧标签只读，右侧 OA/发票 checkbox 可编辑。 |
| `saving_rules` | 保存规则中，禁用重复提交。 |
| `selection_dirty` | 用户已选择银行流水；切换月份、标签、账户、分页或 bucket 必须清空选择。 |
| `submitting` | 批量提交中，等待 operation barrier。 |
| `resetting_submitted` | 正在批量撤回已提交流水规则批次，等待 operation barrier 后刷新未提交候选。 |

## Read Model / Worker 状态

当前 `bank_flow_rule_batch` read model 使用 scoped incremental projection：

- `fresh`：候选、submitted、withdrawn 与 source versions 一致。
- `refreshing`：dirty scope pending/processing。
- `stale`：source version、schema version 或 dependency 变化。
- `failed`：投影失败。
- `unavailable`：SQL/runtime dependency 不可用。

刷新来源：

- 银行流水导入或银行明细标签变化。
- 本模块标签规则保存。
- 本模块 submit/withdraw/reset-submitted。
- Workbench relation 写入、撤回或下游 relation distribution 变化。
