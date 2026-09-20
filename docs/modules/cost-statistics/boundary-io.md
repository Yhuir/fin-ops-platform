# 成本统计边界与 I/O

日期：2026-09-13

## 模块状态

- 状态：closed
- 页面职责：对同一项目成本集合提供项目、银行流水标签、银行账户三个观察维度，并对同一 canonical 银行流水集合提供时间、标签两个收支观察维度。
- 不负责：银行账户余额、银行流水维护、成本专属标签规则、构建 Cost read model。
- 旧路径：原始 `bank` view、`time-tag-rules` API/设置/前端抽屉已经删除，禁止兼容回退；`time|bank_tag` 是当前正式只读 view。

## 分层边界

| 层 | 输入 | 输出 | 禁止 |
| --- | --- | --- | --- |
| Route | HTTP query/body、权限 session | HTTP 状态、JSON 或导出文件 | SQL、业务聚合、队列写入 |
| Canonical repository | scope、一个 PostgreSQL connection | 单个一致性 snapshot | read model、Redis、RabbitMQ、HTTP、逐行查询 |
| Policy | canonical snapshot、标签范围、无 OA/人工分配事实 | 唯一成本事件集合或真实流水集合、聚合、详情 | 数据库、网络、全局状态、fallback |
| Query service | repository、policy、view/filter/cursor | 稳定 API DTO | freshness gate、worker、旧 view 兼容 |
| Manual allocation service | relation case、逐 OA 单元金额、来源/退款/非成本明细、version/fingerprint、actor | versioned allocation 与 audit | HTTP、页面状态、比例建议、半写入 |
| Frontend | API DTO、用户选择 | 五视图、详情、导出、错误/重试；从合法草稿构造单元合计 | 重算服务端统计业务、跨页面 I/O、旧规则 UI |

## Canonical 输入

单个 `REPEATABLE READ READ ONLY` snapshot 按请求范围批量读取。两个流水 view 只读取银行流水和批量有效分类投影并立即返回；三个项目成本 view 再按需读取其余事实。未配置无 OA 项目时，项目成本只加载关系成员，并以同一 snapshot 内的一次基础聚合读取全量流水收支数量和可用年份；该聚合不执行标签分类：

- `app.bank_transactions`
- `app.oa_applications.normalized_payload` 的成本字段和 canonical `expense_items`；尚未进入正式表的 OA 成员通过 `PostgresOaPendingPaymentAdmissionRepository` 读取原始 admission 记录，正式表优先，同一快照批量读取。
- `app.workbench_pair_relations` 中 `status='active'` 的正式关系
- `app.bank_transaction_categories` 与 confirmations 的批量有效分类投影
- `app.app_settings` 中银行账户映射、`cost_statistics_no_oa_projects` 和 `cost_statistics_project_cost_scope`
- `app.cost_statistics_manual_allocations`
- 仅人工分配单条详情/保存读取复杂 OA 关系时，通过关系 repository 的 `load_display_history(oa_ids)` 在同一 snapshot 内一次读取相关正式关系历史；列表、explorer、统计与导出不加载展示历史。

成本模块不读取银行明细页面的 payload/read model。银行有效分类通过银行分类 owner 的批量 projection port 取得；不得复制分类算法或增加 SQL/Python fallback。

OA 成本资格由 Policy 按表单类型和 canonical 审批完成状态判断。`completed_at` / 输出 `oa_completed_at` 仅为可为空的凭据信息，缺失沿用既有空字符串输出，不阻断单据、报销明细或整组成本；不补造时间。Repository 保留原始时间投影，不维护第二套完成状态判断。来源付款日期仍是成本归属年月的唯一日期依据；进行中单元不计成本，但已完成兄弟单元可独立分配；真正缺失关系成员仍不猜测事实，金额或来源未定的部分保留待处理。

## 请求闭环

```text
GET explorer/detail/export
  -> CostStatisticsApiRoutes
  -> CostStatisticsQueryService
  -> PostgresCostStatisticsCanonicalRepository.load_snapshot()
  -> CostStatisticsPolicy
  -> 200 JSON / export file

PUT manual allocation
  -> CostStatisticsManualAllocationService
  -> lock relation facts + validate version/fingerprint/source capacity
  -> allocation + audit.events in one transaction
```

### 人工分配 I/O

- `GET /manual-allocations` 仅返回摘要：关系 ID、项目名集合、OA 单元/银行流水计数、关系合计、状态、原因、版本、可写权限。`counts={pending,allocated}` 与 `row_count/next_cursor` 来自同一关系快照；不在 items 中带 units/bank_events/source_allocations。
- `GET /manual-allocations/{case_id}` 定向读取该关联的完整 OA 单元、银行证据、当前有效分配。返回当前成本范围内支出及其已确认退款份额；完整关系事实仍在 repository 内保留。关系内支出与退款一次批量分类，使用 owner 的 `effective_category_*` 明确映射，不拆斜杠或猜主子标签。
- `PUT` 请求固定为 `relation_case_id, expected_version, scope_version, source_fingerprint, allocations, source_allocations, non_cost_amount, non_cost_reason`。单元合计只接受 `{unit_id,amount}`；来源明细分别为 `cost_lines[{unit_id,bank_transaction_id,amount}]`、`refund_links[{refund_transaction_id,bank_transaction_id,amount}]`、`non_cost_lines[{bank_transaction_id,amount}]`。金额为两位小数字符串；来源行必须正数，零成本单元允许明确 0。
- 选择来源后，银行账户与付款日期只读。OA 行标签取来源；人工补充行通过 cost_tag_code 单独选择成本标签，不写银行分类。OA 费用类型仅作原始凭据。
- 完整分配保持 `C+X=N`；混合审批及已保存的单来源部分决定允许 `C+X≤N`。逐来源不得超分、逐退款必须完整、逐单元来源合计必须与其分配金额相等。部分分配只允许已完成 OA，单元金额不超过原额；等待审批的预算不转成人工成本或非成本。全部完成的普通任务继续在 `O=N` 时固定原额目标。
- 保存先取得既有 relation member locks，再锁关系及来源银行/OA 行，重新核对事实与版本。一次事务写 allocation 和 audit；锁冲突、事实变化、CAS 冲突返回 409，不自动重试提交。
- 0169 只为既有 manual allocation 表增加 nullable JSONB `source_allocations`。旧 NULL 表示没有显式来源决定，只在当前事实确实存在唯一解时推导，不反推历史多对多。
- 标签补齐可复用已保存来源；账户/日期变化仍受既有 fingerprint 保护，可能要求重新确认。单条详情按关联读取，同时检查共享成员关联，避免局部读取漏掉重复归属。
- 来源决定可保存但状态仍 pending（缺标签、账户、日期）。`allocation_stale` 不沿用旧决定；未知来源仅保留待分配任务，不生成正式成本占位行。
- 抽屉按关系缓存会话草稿，切换状态/搜索保留；关闭或显式重读脏草稿沿用确认。提交失败保留输入，成功只按响应状态移动任务。

### 抽屉前端边界

- 容器拥有列表/详情/独立草稿/保存；表单只收任务、草稿、权限和回调，输出编辑/保存事件。sourceAllocation纯工具按来源行构造既有单元金额，不重写服务端政策。
- 固定金额取原始目标；可编辑金额不再保存targets副本，只存来源行和显式zeroUnitIds。来源/金额无效时拒绝构造PUT。
- 证据按详情必有的 `relation_display_groups` 分组，表格行以内部稳定ID保持身份；内部主键不进入可见文字。无字段补猜、演示数据回退或全局样式。
- 详情GET/保存PUT使用现有客户端15秒超时；PUT选择allowHtmlFallback=false。结果不明确时GET核对版本及实际内容，不自动重发PUT。数据库/审计/权限保持既有合同；详情 DTO 的预填扩展见下节。

### Explorer 与日期合同

- `view=time|bank_tag|project|cost_tag|bank_account`；旧 `bank`、`expense_type` view 明确拒绝。
- 三个成本 view 的路径分别为：项目→主标签→子标签→明细；主标签→子标签→明细；账户→项目→主标签→子标签→明细。
- 成本标签筛选使用后端返回的 `bank_tag_primary_key`、`bank_tag_sub_key`；主、子标签身份包含层级，客户端不自行生成。其他上级参数为 `project_name`、`bank_account_label`。
- `time` 直接分页银行流水；`bank_tag` 沿用原 `bank_tag_primary_label/bank_tag_sub_label` 和原始收支口径。
- `bank_tag` 主标签顺序由 Policy 唯一生成：原排序后，若外部往来款付款、收款都存在，则只将收款移动到付款后；其余主标签相对顺序、子标签排序、字段和金额不变。前端按返回顺序展示，不维护第二套排序；无新增数据库或跨页面 I/O。
- 共用 scope/query/cursor/page_size/include_statistics。成本 cursor 版本为 2，并绑定当前项目成本范围 version，原银行 cursor 不变；非法或旧 cursor 返回明确错误。
- 每栏只按上级过滤，同级和祖先可继续切换。summary 保持当前期间/搜索根范围，不随末级选择缩水；row_count 是当前路径分页前行数。
- 成本 facets 使用 projects、bank_accounts、cost_tag_primary、cost_tag_sub；项目/统计使用 primary_tag_count。标签分面返回 key/label/total_amount/row_count/project_count。
- 已分配行 ID 为 `relation:{case}:unit:{unit}:source:{bank}`，金额/账户/主子标签/付款月份同源；来源未知不进入任何正式成本视角/导出；真实已确认来源但缺日期仍在全部期间单列 undated_amount/undated_count。
- 支出按来源实际付款日期归月，跨月付款拆行；退款先归原支出，冲减原付款月成本。银行收支视角的退款日期不变。
- 三个成本根总额一致；两个银行流水根 `total_amount=expense_amount-income_amount`。银行基础统计仍在同快照批量计算；无关流水不加载完整标签。

### 详情与导出

- OA 明细 `/allocations/{id}` 展示来源行金额、真实来源 ID/日期/标签、OA 原额和关系证据；无 OA 与 raw bank 行继续 `/bank-transactions/{id}`。
- preview/download 使用同一 policy 与筛选；成本导出 14 列包含银行账户、主/子/完整路径、来源时间、来源 ID、成本金额、原 OA 与分配状态。
- 项目按月/年导出同时提供按项目汇总与成本明细两张表；preview 列出相同 sheet_names。预览最多 8 行，明细上限 20,000；超限明确失败。
- 删除旧 expense_type 筛选与无效 OA/发票附表参数；携带退役参数明确 400。没有旧分类导出兼容分支。

## 设置边界

- 成本设置包括 `cost_statistics_no_oa_projects` 虚拟项目映射和 `cost_statistics_project_cost_scope` 全局准入。
- `AppSettingsService.get_cost_statistics_source_settings_payload()` 只向 canonical repository 提供银行账户映射和银行标签字典等读取事实。
- 已删除的 `cost_statistics_time_tag_selection` 不读取、不归一化、不持久化、不审计；历史持久化字段不得作为运行时 fallback。

## 文件范围

| 层 | 文件 |
| --- | --- |
| Frontend | `web/src/pages/CostStatisticsPage.tsx`、`web/src/components/cost-statistics/*`、`web/src/features/cost-statistics/*` |
| Route | `backend/src/fin_ops_platform/app/routes_cost_statistics.py` |
| Query / policy | `cost_statistics_query_service.py`、`cost_statistics_policy.py`、`cost_statistics_bank_tags.py`、`cost_statistics_manual_allocation_service.py`、`cost_statistics_source_allocation.py`、`cost_statistics_allocation_scope.py`、`cost_statistics_scope.py` |
| Canonical repository | `cost_statistics_canonical_repository.py` |
| Manual allocation repository | `postgres_repositories/cost_statistics_manual_allocation.py` |
| Settings owner | `app_settings_service.py` |
| Tests | `tests/test_cost_statistics_*.py`、`web/src/test/CostStatistics*.test.*`、`web/e2e/cost-statistics-*.spec.ts` |

## 已删除旧链路

- 原880px卡片布局、可见内部ID、已分/剩余/计算公式、独立targets输入与旧source-popover/evidence-card/target样式。usedBySource仍用于合法来源容量校验。


- OA 费用类型成本分面、导出分类与前端旧状态；整组唯一银行账户推断和整组最后付款月归属。
- `include_cost_row_tags` 开关、标签多字段轮询/斜杠解析、旧单金额抽屉和专属样式、挂载时的额外任务计数读取。

- Cost read model、refresh service、runtime worker、source version、SQL projection与缓存链。
- 原始 `按银行` view 及其前端状态、类型和请求参数。
- `/api/cost-statistics/time-tag-rules` 的 GET/PUT 路由及 App Settings family。
- `time_rows`、`bank_flow_rows`、`bank_flow_time_rows` 响应兼容读取。
- 人工分配银行流水的旧 `summary` DTO、前端 mapper、展示与测试 fixture。

历史 migration 和明确验证“旧合同被拒绝”的负面测试可以保留；生产 runtime 和 UI 不得保留并行旧路径。

## 跨模块影响

- 银行明细：功能不变，继续拥有账户余额、账户维度筛选和流水维护；成本统计只读同一 canonical 流水做时间/标签收支分析。
- Workbench/OA：关系确认、撤回或 OA 状态改变后，下一次 Cost GET 读取新事实；不新增 fan-out。
- 设置：只删除成本统计旧 time/tag family，不影响银行明细自己的自动标签设置。
- 权限/审计：无 OA 与人工分配写入口保持现有权限和审计合同。
- 数据库：0169 增加一个 nullable JSONB 列，不重写旧金额；不创建备份，不删除主库。写入只限成本分配与审计。

## 双表格抽屉界面边界（2026-09-09）

- 容器继续独占 GET/PUT、权限、草稿、未知保存结果核实及刷新；本轮没有新增 HTTP、DTO、数据库、worker 或 read model。
- `CostSourceEvidence.tsx` 接收 task 和来源错误展示，只读 OA 成本单元与流水，两侧计数按事实条目。当前统一对照表的边界见文末；旧双 FinanceTable 已被替换。
- `CostSourcePicker.tsx` 接收 options/value/disabled/error、输出 transactionId；使用 HeroUI Popover/ListBox，不请求网络、不分配金额、不推断账户或标签。
- 表单仍接收 task/draft、输出 onChange/onSave；`sourceAllocation.ts` 错误键分为 source/amount/owner，保留精确金额、零、双边闭合及未知写结果核实。
- OA 原费用类型只读展示；成本行标签只读来源流水结构化主/子标签。替换来源不改变已输入金额。
- 已移除 OA 文章卡片及展开全文行、独占一行的新增入口、来源格内联金额错误、旧原生 select 及灰白展开覆盖样式。旧实现没有并行保留。

## 待确认来源预填与合并单元格（2026-09-10 修复）

- `GET /manual-allocations/{case_id}` 新增必有的 `suggested_source_allocations: null | {cost_lines,refund_links,non_cost_lines}`；`PUT` 响应该字段为 null，列表摘要不携带它。PUT 入参、存储、权限、审计及原有自动完成规则不变。
- repository 在成本 snapshot（总表、任务及详情）投影银行 raw_payload 中现有的 `source_oa_row_id`、`oa_row_id`、`derived_from_oa_id`、`source_workbench_row_id` 四个标量引用为内部 `source_oa_ids`。仅投影这四个标量，普通 explorer 和任务列表不取完整原始 payload、不增加银行查询。只识别与当前 canonical OA ID 精确匹配的引用；别名或互相冲突的引用不猜测。
- `suggest_source_allocations(task, bank_rows, relation_groups)` 是详情专用无 I/O 纯函数。只处理版本0、未保存、未过期、固定目标且无退款/非成本的 pending 任务；输入合计必须闭合。枚举一单元对应整笔来源子集、一来源对应固定单元子集，按候选重叠划分独立组件，逐组件搜索完整覆盖；只有唯一覆盖输出建议。搜索到两个解即判定该组件歧义，不能取局部贪心匹配或前两个解的公共行。没有候选的部分保持人工。
- 固定上限为128个正成本单元与来源节点合计、50000步候选/覆盖工作；超限返回null，绝不把截断搜索当唯一解。只在展开详情计算，列表与explorer不计算、不增查询。没有通用求解器、依赖、新缓存/worker/表。
- 当前有效历史子关系先约束来源允许归属的 OA，原始明确引用与其取交集；冲突或无法解析的引用不按金额绕过。当前精简OA投影不含足够的外部身份别名，继续只接受canonical引用，不伪造别名。退款缺少逐来源归属证据，非固定成本缺少确定目标，这两类不生成金额建议，保留完整人工编辑/保存链。
- Workbench 的 `exact_amount` / `unique_bank_sum` 是展示对齐，不作为来源证据；不新增子集合搜索、比例算法、hash、表、cache、worker 或 fallback。截图 CASE-AUTO-0016 的金额组合可以作为人工判断线索，但没有原始明确引用时不会自动预填。
- 服务只在 GET 详情计算建议，不把建议送入 policy、统计或持久化。前端草稿初始化保留确定来源，版本0时合并剩余建议；人工版本只使用已保存来源，stale 不复用。已有会话草稿（包括手动删空）不重新初始化。最终保存继续完整校验来源和金额并使用既有事务/版本约束。
- 同一成本单元的项目格和 OA 格使用原生 rowSpan；新增、删除来源后同步更新跨度，删除最后一条仍保留身份与新增入口。不同 OA/成本单元不因项目同名而合并。
- Block 使用四色循环 `#C5D4B8` / `#E8C5A5` / `#DDB9C3` / `#B9CCDF`；数据表格与输入保持白底，颜色不表示财务状态。已删除旧两色选择器、续行空身份格及依赖首个 td 的项目样式，不保留重复路径。
- 上游 Workbench、银行分类与账户页面的写入、DTO 和职责不变；Cost 只消费既有原始引用。read model / worker 合同不变。本轮没有数据库迁移或备份。

## 来源菜单布局与禁用展示（2026-09-10）

- 来源选项高度随内容增长且不参与纵向压缩，菜单限高滚动；银行名称/交易对方/标签可换行，金额保持完整。样式只作用于 CostSourcePicker，不修改公共 ListBox。
- 已用完及同项重复来源保留灰色及真实禁用状态，不显示“已用完／本项已使用”。部分可用、当前行已选中与金额释放后的判断继续由表单拥有；Picker 接收 isSourceDisabled(lineId, sourceId): boolean，输出来源 ID，HTTP 和金额规则不变。
- 删除旧 disabledReason 字符串回调、原因文字节点及 cost-source-option-state 样式；不保留旧属性或兼容分支。

## 正式关系对照与金额提示（2026-09-13 更新）

- `sourceEvidence.ts` 是无 I/O 的索引投影函数：输入任务事实及 `relation_display_groups`，输出原始索引分组；未知 ID 明确失败。删除按草稿 owner/source 边构建连通组的旧逻辑，不读取金额、不推导配对。
- `CostSourceEvidence.tsx` 用局部原生语义表格展示该分组：一对一同行，一对多/多对一 rowspan，多对多明确组标题并独立列出两侧事实。每项事实仅出现一次，序号保持来源列表顺序；上方不随草稿选择、金额或非成本决定重新分组。范围外流水按既有成本范围裁剪，已被范围排除的来源位置显示“—”，不误称未配对。无效输入的错误责任仍在既有校验。
- OA 白底、流水浅灰底与中央分隔线共同区分两侧；表格在窄屏内部横向滚动，外部抽屉及保存区不溢出。样式作用域只在成本模块。`React.memo` 比较来源身份，金额输入不重画未变化的证据表；不新增缓存层、依赖或网络请求。
- 表单复用 `validateSourceDraft` 的完整错误集合，全部通过且不在保存/错误/提示状态时，保存按钮左侧显示深绿色“分配金额一致”。逐来源、逐单元、退款、非成本和精度规则保持原样；不另造金额判断、自动保存或成本准入规则。
- 已删除旧的独立双表渲染及对应两栏/公共表格覆盖样式，不保留并行展示路径。FinanceTable 公共实现、API、存储、权限、审计、worker/read model 均无变化；本轮不创建数据库备份。

## 抽屉文案精简（2026-09-10）

- 移除对照表上方的常驻说明及 cost-evidence-caption 样式；多对多组标题简化为“多对多 · N 项 / M 笔”，不改分组逻辑与事实展示。
- 只读、加载、空态、冲突和保存待核实使用短文案；重读按钮改为“重新加载”。已保存、未保存与保存结果未确认保持区别，既有修改保护、权限、校验、超时与核实流程不变。
- 保留状态徽标、“未保存”、金额一致提示及银行信息缺失等必要反馈。列表切换仍沿用现有异步流程，不因文案调整更改数据加载或其他页面。
- 无新增 I/O、依赖、状态层、数据库备份或门禁；仅成本模块内部 Picker 禁用回调从字符串改为布尔值。

## 全局标签范围 I/O

- `GET /api/cost-statistics/project-cost-scope` 返回 `version,selected_tag_codes,available_tags,can_save`；清单包含系统内部往来、现行/归档规则及未标记，普通收入 `can_select=false`。
- `PUT` 只接受 `expected_version,selected_tag_codes`；沿用成本页写权限，actor 来自 session。未知/重复/收入代码 400、权限不足 403、版本冲突 409。相同选择 `changed=false`，无重复审计。
- Settings service 使用既有 settings 锁及 versioned family repository，读取字典、验证、只合并本 family、审计在同一 PostgreSQL 事务。其他设置 writer 保留最新范围。0170 仅在键缺失时初始化；空数组持久有效，GET 不补默认。
- Policy 通过成本专用纯函数生成范围内来源、退款份额、金额与任务状态；正式成本、任务详情、来源建议及保存校验使用相同范围。一次构造标签集合，不增加逐行 SQL。无 OA 成本取虚拟映射与此范围交集。退款跟随已确认原支出，不按收入标签切断。
- 任务详情只返回当前可分配范围；对照表、来源菜单、计数及金额同源，不显示“范围外”。全范围外关系从列表/计数排除，按 ID 读取为零可用来源，不能保存。原始银行事实、关联及范围外已保存来源仍完整保留。
- 专用 Drawer 只接收数据与事件。页面拥有 GET/PUT、草稿、超时结果核实和成功后的本页失效；旧分页请求中止、路径重置，保留期间/搜索。不开新队列、缓存或跨页面请求。
- 移除旧 source_pending 正式行生成、分面、导出状态和详情显示分支；保留现有来源 fingerprint、金额校验、事务与正式发布措施。

### 五视角展示边界（2026-09-14）

`CostStatisticsHierarchy` 接收每栏的 title、selectedKey、items（key、label、meta、可选 secondary）、loading、emptyLabel 与 onSelect，以及 detailTitle/navigationLabel 和明细插槽。meta/secondary 只承载页面准备的展示内容：成本单金额或流水收支与计数。输出选择事件和布局，不读取 API、不识别业务 DTO、不聚合金额。页面仍拥有查询、取消、选择与分页状态；列表复用 HeroUI ListBox 的键盘选择模型；内容区保留原生指针拖选，复用已有 hasSelectedTextWithin 判断，复制不触发下钻，普通点击及重复激活已选项均进入对应下一级。

项目成本与银行标签共用层级布局，按时间保持单表并共用成本页高度/明细规则。工作区根节点限定祖先高度、内部滚动与紧凑样式；离页卸载后恢复其他页面默认布局。公共 App Shell/FinanceTable 和分配抽屉样式不变。已删除银行视角旧高度变量、独立标签布局和日期 Chip/compact 双路径，不保留兼容回退。无 API、服务、存储、权限、worker 或业务金额 I/O 变化。


## 待分配范围闭环（2026-09-11）

- `cost_statistics_allocation_scope.py` 仅拥有无 I/O 的任务投影、已覆盖来源校验与保存合并。输入完整任务/来源决定，输出范围内任务或合并后的来源决定；不分类、不读数据库、不修改公共银行/关联输入。
- 所有任务 DTO 增加 `scope_version`，PUT 必须携带。保存读取设置时使用 SHARE 行锁，与范围设置写入串行；版本漂移 409，非法版本 400。沿用分配 CAS、来源 fingerprint、成员锁及审计事务，不新增 hash 或存储。
- 当前编辑按范围内完整/部分分配规则及逐来源/退款/单元校验。未保存的歧义任务不能因范围缩小自动确认；可提供现有详情建议。历史有效来源按范围投影金额，不把截取后的来源金额强制恢复成完整 OA 原额。
- 保存按来源 ID 替换范围内决定，保留范围外仍有效的成本/退款/非成本来源。持久化金额汇总覆盖已保存来源，不要求尚未分配的范围外银行金额闭合；单位身份保留完整集合。重新勾选后，新来源继续待分配，已确认来源仍进入统计，不清空已有成本。
- OA 只在已有来源明确完全属于范围外、且当前来源均已明确时从任务隐藏；未知来源不按金额或序号猜 OA。历史失效分配不用于合并。既有 NULL 来源记录若不能定位范围外原决定，范围内保存明确拒绝覆盖，需先在完整范围确认来源；不猜测历史来源。
- 跨范围退款按已确认退款链接分摊显示金额；归属不明返回 `scope_refund_required`，禁止猜测或保存错误净额。完整付款/退款仍可在关联台查看。
- 删除旧范围外标记及待分配全量流水口径；原始银行两个视角、关联台、银行明细、无 OA 范围、权限与导出列结构不变。无迁移、备份、worker、缓存或新依赖。


## 待分配正式关系读取闭环（2026-09-13）

- 事实源为当前 active relation typed members、canonical OA/银行以及相关正式历史。Cost 与 Workbench 共用 `apply_display_subgroups` 和关系 repository 的历史查询，不从 Workbench 页面接口、旧分配、缓存或草稿反推关系。
- `GET /manual-allocations/{case_id}` 和成功 `PUT` 的任务 DTO 必有 `relation_display_groups[{unit_ids,bank_transaction_ids,sources_excluded}]`；列表摘要不携带该字段。分组先基于完整关系计算，再按当前成本范围裁剪，保持一对多/多对多与共有父 OA 边界。报销子单元共享父 OA 的银行证据，不因此补造逐项来源金额。
- 打开抽屉、展开任务、搜索/状态切换、页面重新激活、已有领域刷新、范围保存与窗口重新获得焦点时重新读取；AbortController 丢弃过期响应。这里的实时指当前 GET 读取最新已提交事实，并在上述交互边界刷新，不增加轮询、WebSocket 或后台任务。
- 干净草稿按新详情初始化；脏草稿/保存结果待核实保留。关系版本、来源 fingerprint、范围版本或分配版本变化时，上方更新事实、下方停止保存并提示重新核对；显式重新加载经既有草稿确认后恢复编辑。读取失败明确显示错误，不能把旧任务当作可保存的新事实。
- 删除详情“有缓存就不读”、范围刷新直接清空草稿和草稿驱动证据分组的旧路径。保留权限、来源校验、事务、成员锁、现有版本/fingerprint 与未知写结果核实机制。
- 不改变成本准入、分配存储/PUT 入参、银行原始视角、关联确认/撤回命令或 read model/worker。无迁移、数据库备份、新依赖或新增门禁。


## 正式子关系约束预填（2026-09-13）

- 成本 snapshot 复用 `relation_history_partitions` 解析精确 case ID + typed members 的正式合并历史，返回内部 `source_relation_groups[{oa_row_ids,bank_row_ids}]`。历史中的 OA+流水子组提供边界，其余未归属成员保持当前关系范围；2026-09-14 起所有成本读取入口共用该证据，自动计算与详情建议分别消费。此字段不进入 HTTP DTO 或持久化。
- Workbench 展示与 Cost 共用历史分组解析；金额对齐后的 `display_subgroups.resolved` 不作为来源证据。历史成员不匹配时不得采用旧分组；不复制历史解析或按屏幕顺序推断。
- 详情预填将历史子组约束与现有原始 OA 引用取交集，阻止不同子组的重复金额互相成为候选。多个费用子单元仍使用固定目标及完整唯一性判断，不平分、不任意切分、不改变自动完成或保存规则。
- 删除详情预填忽略历史边界、仅用全组金额候选的旧调用路径。沿用 128 节点/50000 步上限、来源与金额校验、权限、CAS、现有 fingerprint、事务及审计；不新增 gate/hash/cache/worker、数据库字段或查询。
- 预填仅初始化未保存草稿；上下证据、编辑保护、范围刷新和保存重读保持既有边界。本次无数据库迁移或备份。

- 保存后相同版本、相同关系/范围且状态未变的刷新保留已确认保存提示；事实变化或显式重载清除提示。不会阻止读取或恢复旧草稿。

## 人工补充 I/O（2026-09-13）

- GET/PUT `/api/cost-statistics/manual-allocations/{case}` 增加 `manual_items`；GET/成功 PUT 同时返回 `manual_options{projects:[{id,name}],tags:[{code,label,primary_label,sub_label}]}`。列表摘要不含目录、明细，搜索/项目名称覆盖人工行。
- PUT 的人工元数据只接受 `{unit_id,project_name,expense_content,cost_tag_code}`，`unit_id=manual:<UUID4>`，最多200条；内容1–500字，项目/标签必须有效。响应另带服务端项目与成本标签名称。金额仍只通过既有 `allocations` / `source_allocations.cost_lines` 提交，不在元数据复制金额。
- 人工 ID 不是 OA ID；每个人工项必须有且只有一条正数两位小数成本来源。来源必须属于当前任务范围内支出，逐笔成本+退款+非成本等于流水原额。前后端共同核对，最终以事务内 canonical 校验为准。
- Repository 在既有 allocation 表新增0171 `manual_items jsonb not null default []`；同一事务保存来源、元数据、版本与审计。目录由定向详情事务批量读取 OA 项目标识/名称、设置和标签；不让前端调用 OA provider，不增加 worker/cache/read model。
- 保留现有 relation/source/scope/version 冲突机制。旧客户端省略 manual_items 且已有人工记录时明确409，禁止静默丢弃。范围外人工项与对应来源一同保留，范围内删除仅在新的完整有效分配保存后生效。关联/金额变化使原决定失效，不自动重用旧人工成本。
- 查询生成 `row_kind=manual_allocation`，详情 `kind=manual_allocation`、`oa_original_amount=null`、OA ID空；人工金额进入三个成本视角和原有导出，银行流水视角不变。成本标签覆盖不参与来源范围准入，准入仍按原银行有效标签。
- 不写 `oa_applications`、银行金额/分类或 Workbench 关系；不修改其它页面 I/O。普通 OA 与历史有效分配沿用原路，无并行旧人工实现。

人工成本项目选择包含已有的已完成项目，支持历史成本补录；项目完成状态不作为成本补录限制。标签仍取当前有效标签，历史保存但已停用的标签只允许原条目保留。

人工成本项目选择与现有成本统计一致，以 canonical 项目名称为维度；保存提交 `project_name`，服务端按当前目录验证。历史 OA 只有名称而无项目 ID 时合法，输出 `project_id` 保持空，不伪造 ID、不调用外部项目服务、不修改 OA。目录包含头表与费用明细的项目名称。

## 人工成本标签目录与二级菜单（2026-09-13）

- 人工成本的 GET 详情、成功 PUT 与保存验证统一复用 `BankTransactionCategoryService.auto_tag_rules_payload` 的 active rules + system internal_transfer，与银行明细人工分类目录一致。按结构化 output_primary_label/output_sub_label 输出；空子标签保持空。旧业务定义仍保留在设置中，不再进入新建人工成本目录；停用或退出目录的已保存条目仍可原样保留。
- 新增 `GET /api/cost-statistics/manual-tags`，沿用成本读取权限，返回 `{tags:[{code,label,primary_label,sub_label}]}`。Settings owner 每次从持久设置读取，只输出目录，无凭据、规则条件、OA/银行扫描或预填计算；保存仍在原事务中使用当前目录验证。无 schema/worker/read model 改动。
- 抽屉容器拥有目录请求、取消与错误状态，选择器打开时读取；成功只更新任务的 manual_options.tags，不覆盖草稿。失败不展示旧选项，允许重试。金额编辑和主标签切换不请求目录。
- `CostManualTagPicker` 仅接收目录/选中值/加载状态/错误并输出打开、重试和选择事件，不拥有 HTTP 或银行分类写入。左主右子，单层直接选择，名称内斜杠不拆层级，标签身份始终为 code；菜单限高、内部滚动、弹层避让窗口边界。
- 删除人工原生 select 和 path 拼接标签名称路径；不修改成本范围字典、银行明细、关联台或公共 ListBox。人工标签不改变来源有效银行标签和范围准入。历史金额、原 OA 与关系不写入。

### 混合审批状态 DTO 与保存边界（2026-09-13）

- 详情返回 `allows_partial, waiting_oa_ids`，单元返回 `cost_eligible`；来源有明确 OA 引用时，混合任务返回 `allowed_unit_ids` 约束，空数组表示不属于已完成单元，不伪造归属。`unallocated_amount` 为当前可分配净支出减已分成本及非成本。
- PUT 复用原请求与 storage，进行中单元提交 0；剩余金额不存为新成本类别。保存仍按当前 snapshot 校验状态、scope/version、来源容量并原子写 allocation/audit。审批状态不加入原有财务 fingerprint，避免同组审批完成使已保存金额整体过期；当前资格每次重新判断。
- 保存沿用 member locks、银行与正式 OA SHARE locks，并锁定相关 admission 行。正常 GET 无行锁。没有新表、迁移、read model、缓存或 worker。
- 删除旧 `incomplete_oa_relation` 整组排除分支。保留成员完整性、重复归属、权限、事务及范围保护；关联台、银行明细与 OA 同步写路径不变。

## 确定来源自动分配 I/O（2026-09-14）

- Cost repository 的列表/explorer 只为无人工记录且存在多银行来源的关系批量读取所需正式 history；详情与事务内保存重读保留展示所需完整历史。复用 `relation_history_partitions` 一次解析生成内部 `source_relation_groups`。详情显示继续复用原显示投影，热路径不调用展示金额对齐。原银行视角不读取关系 history。
- `automatic_relation_sources` 只拥有证据限定的独立组件计算，复用 `automatic_source_allocations`；不读写数据库、不枚举金额子集。相同候选 OA 集合只索引一次，避免构建银行×OA 矩阵。证据冲突阻止相关组件自动计算。
- 完整当前关系只有一笔支出时，保留当前全部 OA 目标；历史子组可能早于后来追加的 OA，不能据此排除新成员。正式历史只在多支出间限定范围，明确 canonical 引用仍参与限制；不采用“先失败再回退”的双计算路径。
- Policy 与范围投影区分固定目标与部分确定金额，自动结果用现有 `source_allocations/status/pending_reasons` 返回；部分来源不松动原 OA 目标。自动任务也提供既有 fingerprint/version，已完成可查询和首次人工编辑。原 fingerprint 计算口径不变。
- 详情建议只对版本0未解决部分计算；前端草稿初始化合并互不重叠的确定行和建议。版本大于0的有效人工决定优先，仍使用原 CAS/事务/审计与范围外决定保留。
- 已删除详情独占来源证据、外层多对多直接拒绝自动、自动完成提前返回缺身份、自动任务排除于已完成列表的旧路径。金额组合建议仍是人工业务能力，不作为自动结果或兜底。
- HTTP 路径、PUT/持久化形状、权限、上游关系/银行写入不变。无迁移、备份、read model、cache、worker、新依赖或新 gate。


## 人工分配折叠呈现（2026-09-15）

待分配和已完成共用 HeroUI Accordion，单个受控 expanded 状态负责切换；展开沿用原详情 GET，收起不提交、不修改草稿。原生面板负责过渡及隐藏，局部 AllocationPanel 仅观察内容尺寸以衔接异步详情/表单行变化，并在原生隐藏后释放表单；观察器随组件或状态清理。收起时 inert 阻止隐藏控件交互，草稿继续归抽屉所有。无全局样式、HTTP、权限、保存、数据库或 worker 变化。

已移除旧 article/button 条件挂载路径和箭头 is-expanded 规则，不保留平行折叠实现。验证入口为 CostManualAllocationRefresh.test.tsx 和 cost-source-allocation.spec.ts，包含动态中间帧、延迟详情、反向切换、减少动态效果和大明细卸载。

## 右侧抽屉交互（2026-09-15）

本模块复用的右侧抽屉遵循[统一关闭行为](../../dev/right-drawer-dismissal.md)：外部点击/Esc 不关闭，X 继续执行已有关闭保护。业务 owner 持有保存/确认完成状态，公共 AppDrawer 仅展示 `completion`；不改变本模块后端 API、权限、事实写入及查询 I/O。旧的重复退出按钮和成功自动关闭路径已移除，内部编辑取消仍按局部职责处理。

## 2026-09-20 付款展示证据一致性

Cost 的关系展示复用统一 OA—银行对应规则；canonical repository 在原批量读取中提供申请日期、银行日期、币种、账号和明确来源的最小字段。原始关系历史解析、source_relation_groups、成本资格、来源容量与金额分配保持独立，不能把展示推断当成成本来源。无新增查询、写入、页面刷新或 API。
