# 流水规则批量处理状态机

> `/bank-flow-rule-batches` 只调用页面专属 API。列表、summary 和分页在同一 PostgreSQL snapshot 读取 canonical facts、请求内实时推导候选；正式详情读取持久化历史，live candidate 详情按列表项月份从同一 canonical builder 重算。页面没有 read-model freshness、refresh enqueue、202 reconcile 或后台轮询状态。

## 标签规则状态

| 状态 | 事实源 | 语义 | 允许流转 |
| --- | --- | --- | --- |
| `active_tag_defaulted` | bank-details active tag + 缺少本模块规则 | 默认 `requires_oa=true`、`requires_invoice=true`，不进入本页候选。 | 保存规则后进入 `configured`；标签归档后进入 `inactive_tag_ignored`。 |
| `configured` | `app_settings.bank_flow_rule_batch_tag_rules` | 已保存明确 OA/发票要求。 | PUT 以 CAS 保存新版本；归档后进入 `inactive_tag_ignored`。 |
| `inactive_tag_ignored` | bank-details tag inactive/archive | 不再用于新候选；历史批次保留提交时 snapshot。 | 标签重新 active 时按 code 复用规则；无规则则回到 defaulted。 |

规则含义：

- 只有 active 且 `requires_oa=false`、`requires_invoice=false` 的标签进入本页未提交资格集合。
- `requires_oa` / `requires_invoice`、标签文本和行级分类在 relation 创建时冻结；已提交/历史不回查当前设置改写。
- 完全相同的保存是 no-op；语义变化使用版本 CAS 并写审计。
- 资格集合变化只返回信息性的受影响月份；不产生本页面 dirty/outbox。保存成功后前端清空旧选择并执行一次正常 GET。

## 批量状态

| 状态 | 事实源 | 语义 | 允许流转 |
| --- | --- | --- | --- |
| `candidate` | 请求内 live builder + 当前银行/标签规则事实 + active relation | 当前筛选下实时生成、可提交且未被 active relation 占用；不是持久化状态。详情使用 `batch_id + scope_month` 从同一 builder 确定性重算。 | 用户选择后进入 `selected_draft`；提交后进入 `submitted`。 |
| `document_flow_only` | 当前标签规则 | 需要 OA、发票或缺少双 false 规则，不属于本页未提交候选。 | 规则未来改为双 false 且无 active relation 时可重新成为 candidate。 |
| `selected_draft` | 页面本地状态 | 用户本次选择，尚未写事实。 | 提交成功进入 `submitted`；清空或切换筛选回到 candidate。 |
| `submitted` | `app.bank_flow_rule_batches` + `app.workbench_pair_relations.status='active'` | relation command 已原子创建正式关系。 | withdraw/reset 后进入 `withdrawn`。 |
| `withdrawn` | batch event + cancelled relation | 历史批次保留，银行流水释放。 | 当前事实仍合格时，下一次 GET 同时实时生成新的 candidate；再次提交走新 command。 |
| `blocked` | service validation | 重复、跨月、跨账户、混合标签、占用、CAS、权限或写入失败。 | 修复输入或重新读取后再提交。 |

提交规则：

- live candidate submit 必须携带合法 `scope_month`；提交事务内按 candidate identity 重读并重算银行流水身份、成员、金额、分类、规则和 active relation 占用，遗留 persisted draft 必须返回 conflict。
- active relation 只从 `app.workbench_pair_relations` 读取，禁止使用 Workbench page read model 或 relation projection。
- 内部转账必须保持一收一支、不同账户、48 小时窗口；批次金额只计单边金额。跨月配对由最早成员月份唯一拥有，±2 天窗口只用于发现配对，后一个月份不得生成重复 candidate。
- submit/submit-selection/withdraw/reset 必须继续通过 relation command、占用检查、幂等/CAS、审计和 changed-batch delta writer 原子提交。`submit-selection` 携带列表项 `scope_month`，并从同一个 canonical source 取得流水、分类、标签 requirement 与 active relation；写事务同时重算 selected-row proof 和 rule proof。PostgreSQL 由 `save_bank_flow_rule_batch_mutation(...)` 持有唯一 caller-owned transaction，relation/history 与 batch/events 共用该 transaction；任一步失败整体 rollback。
- submit-selection 的初读与事务内重读时间证明统一到 UTC 秒级时刻；无时区业务时间按 `Asia/Shanghai` 解释。只有表面格式从空格时间变为 ISO 8601 offset 不构成漂移，真实时刻、金额、标签、账户、成员或占用变化仍 fail closed。
- reset 使用一次 bulk relation cancel 和一次 batch delta 保存；禁止手写 SQL 改状态。
- 每次写成功后，当前页只执行一次普通列表 GET。

## 关联台展示状态

| 状态 | 判定 | 语义 |
| --- | --- | --- |
| `unpaired` | 无 active relation，或 active relation 的冻结 requirement 未满足 | 无 owner 时为 singleton；有 owner 时保持同 case 并显示待补类型。 |
| `paired` | active formal relation 且冻结 requirement 已满足 | relation 完整成员进入已配对区。 |
| `collapsed` | relation 内银行流水数 `>3` | 默认显示 bank-flow summary，原始行位于 `collapsed_rows.bank`。 |
| `expanded` | 银行流水数 `<=3` 或用户展开 | 展示原始银行流水。 |

禁止根据当前规则追溯重分 existing relation，也禁止前端本地推断 paired/unpaired。

## UI 状态

| UI 状态 | 语义 |
| --- | --- |
| `loading` | 初次加载规则、列表或详情。 |
| `empty` | canonical 查询成功且筛选范围没有批次。 |
| `error` | API、权限或参数失败；显示可重试错误，不伪装空态。 |
| `editing_rules` | 抽屉打开；标签列只读，OA/发票 checkbox 可编辑。 |
| `saving_rules` | 规则保存中，禁用重复提交。 |
| `selection_dirty` | 已选择银行流水；切换月份、标签、账户、分页或 bucket 清空选择。 |
| `submitting` | command 进行中；成功后执行一次列表 GET。真实 candidate conflict 时清空旧选择/详情并执行一次列表 GET，提示用户重新选择；不自动重试 POST。 |
| `resetting_submitted` | bulk withdraw 进行中；成功后执行一次列表 GET。 |

列表响应只包含 `summary`、`batches`、`pagination`。一次请求中的 rows、total 和 summary 必须处于同一显式 `REPEATABLE READ / READ ONLY` snapshot；repository 以固定数量集合查询读取请求月份窗口，application service 对同一 live candidate 集合执行过滤、排序和分页。

页面自动选择 live candidate 后，详情请求必须携带该列表项的 `scope_month`；搜索、切换 bucket 或分页后不得用旧月份读取新 batch。live candidate 已被占用、分类变化或不再合格时，详情返回明确错误并由页面刷新列表，禁止读取或恢复旧 persisted draft。
