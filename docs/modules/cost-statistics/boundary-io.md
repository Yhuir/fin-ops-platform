# 成本统计边界与 I/O

日期：2026-09-11

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
- `app.oa_applications.normalized_payload` 的成本字段和 canonical `expense_items`
- `app.workbench_pair_relations` 中 `status='active'` 的正式关系
- `app.bank_transaction_categories` 与 confirmations 的批量有效分类投影
- `app.app_settings` 中银行账户映射、`cost_statistics_no_oa_projects` 和 `cost_statistics_project_cost_scope`
- `app.cost_statistics_manual_allocations`

成本模块不读取银行明细页面的 payload/read model。银行有效分类通过银行分类 owner 的批量 projection port 取得；不得复制分类算法或增加 SQL/Python fallback。

OA 成本资格由 Policy 按表单类型和 canonical 审批完成状态判断。`completed_at` / 输出 `oa_completed_at` 仅为可为空的凭据信息，缺失沿用既有空字符串输出，不阻断单据、报销明细或整组成本；不补造时间。Repository 保留原始时间投影，不维护第二套完成状态判断。来源付款日期仍是成本归属年月的唯一日期依据；进行中、关系成员不完整、金额或来源未定的处理不变。

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
  -> lock relation facts + validate version/fingerprint/C+X=N
  -> allocation + audit.events in one transaction
```

### 人工分配 I/O

- `GET /manual-allocations` 仅返回摘要：关系 ID、项目名集合、OA 单元/银行流水计数、关系合计、状态、原因、版本、可写权限。`counts={pending,allocated}` 与 `row_count/next_cursor` 来自同一关系快照；不在 items 中带 units/bank_events/source_allocations。
- `GET /manual-allocations/{case_id}` 定向读取该关联的完整 OA 单元、银行证据、当前有效分配。关系内支出与退款一次批量分类，使用 owner 的 `effective_category_*` 明确映射，不拆斜杠或猜主子标签。
- `PUT` 请求固定为 `relation_case_id, expected_version, source_fingerprint, allocations, source_allocations, non_cost_amount, non_cost_reason`。单元合计只接受 `{unit_id,amount}`；来源明细分别为 `cost_lines[{unit_id,bank_transaction_id,amount}]`、`refund_links[{refund_transaction_id,bank_transaction_id,amount}]`、`non_cost_lines[{bank_transaction_id,amount}]`。金额为两位小数字符串；来源行必须正数，零成本单元允许明确 0。
- 选择来源后，银行账户、银行主/子标签与付款日期只读；不接受独立标签/银行字段。OA 费用类型仅作原始凭据。
- 保留 `C+X=N`，并校验逐来源、逐退款和逐单元闭合；`O=N` 时逐单元目标必须等于 canonical OA 原额。
- 保存先取得既有 relation member locks，再锁关系及来源银行/OA 行，重新核对事实与版本。一次事务写 allocation 和 audit；锁冲突、事实变化、CAS 冲突返回 409，不自动重试提交。
- 0169 只为既有 manual allocation 表增加 nullable JSONB `source_allocations`。旧 NULL 表示没有显式来源决定，只在当前事实确实存在唯一解时推导，不反推历史多对多。
- 标签补齐可复用已保存来源；账户/日期变化仍受既有 fingerprint 保护，可能要求重新确认。单条详情按关联读取，同时检查共享成员关联，避免局部读取漏掉重复归属。
- 来源决定可保存但状态仍 pending（缺标签、账户、日期）。`allocation_stale` 不沿用旧决定；未知来源仅保留待分配任务，不生成正式成本占位行。
- 抽屉按关系缓存会话草稿，切换状态/搜索保留；关闭或显式重读脏草稿沿用确认。提交失败保留输入，成功只按响应状态移动任务。

### 抽屉前端边界

- 容器拥有列表/详情/独立草稿/保存；表单只收任务、草稿、权限和回调，输出编辑/保存事件。sourceAllocation纯工具按来源行构造既有单元金额，不重写服务端政策。
- 固定金额取原始目标；可编辑金额不再保存targets副本，只存来源行和显式zeroUnitIds。来源/金额无效时拒绝构造PUT。
- 证据按oaId分组，表格行以内部稳定ID保持身份；内部主键不进入可见文字。无字段补猜、演示数据回退或全局样式。
- 详情GET/保存PUT使用现有客户端15秒超时；PUT选择allowHtmlFallback=false。结果不明确时GET核对版本及实际内容，不自动重发PUT。数据库/审计/权限保持既有合同；详情 DTO 的预填扩展见下节。

### Explorer 与日期合同

- `view=time|bank_tag|project|cost_tag|bank_account`；旧 `bank`、`expense_type` view 明确拒绝。
- 三个成本 view 的路径分别为：项目→主标签→子标签→明细；主标签→子标签→明细；账户→项目→主标签→子标签→明细。
- 成本标签筛选使用后端返回的 `bank_tag_primary_key`、`bank_tag_sub_key`；主、子标签身份包含层级，客户端不自行生成。其他上级参数为 `project_name`、`bank_account_label`。
- `time` 直接分页银行流水；`bank_tag` 沿用原 `bank_tag_primary_label/bank_tag_sub_label` 和原始收支口径。
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
| Query / policy | `cost_statistics_query_service.py`、`cost_statistics_policy.py`、`cost_statistics_bank_tags.py`、`cost_statistics_manual_allocation_service.py`、`cost_statistics_source_allocation.py`、`cost_statistics_scope.py` |
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
- `CostSourceEvidence.tsx` 接收 task、当前草稿 costLines/nonCostLines 和来源错误展示，只读 OA 成本单元与流水，两侧计数按事实条目。当前统一对照表的边界见文末；旧双 FinanceTable 已被替换。
- `CostSourcePicker.tsx` 接收 options/value/disabled/error、输出 transactionId；使用 HeroUI Popover/ListBox，不请求网络、不分配金额、不推断账户或标签。
- 表单仍接收 task/draft、输出 onChange/onSave；`sourceAllocation.ts` 错误键分为 source/amount/owner，保留精确金额、零、双边闭合及未知写结果核实。
- OA 原费用类型只读展示；成本行标签只读来源流水结构化主/子标签。替换来源不改变已输入金额。
- 已移除 OA 文章卡片及展开全文行、独占一行的新增入口、来源格内联金额错误、旧原生 select 及灰白展开覆盖样式。旧实现没有并行保留。

## 待确认来源预填与合并单元格（2026-09-10 修复）

- `GET /manual-allocations/{case_id}` 新增必有的 `suggested_source_allocations: null | {cost_lines,refund_links,non_cost_lines}`；`PUT` 响应该字段为 null，列表摘要不携带它。PUT 入参、存储、权限、审计及原有自动完成规则不变。
- repository 仅在定向关系 snapshot 投影银行 raw_payload 中现有的 `source_oa_row_id`、`oa_row_id`、`derived_from_oa_id`、`source_workbench_row_id` 四个标量引用为内部 `source_oa_ids`。普通 explorer 和任务列表不取原始 payload、不增加查询。只识别与当前 canonical OA ID 精确匹配的引用；别名或互相冲突的引用不猜测。
- `suggest_source_allocations(task, bank_rows)` 是详情专用无 I/O 纯函数。只处理版本0、未保存、未过期、固定目标且无退款/非成本的 pending 任务；输入合计必须闭合。枚举一单元对应整笔来源子集、一来源对应固定单元子集，按候选重叠划分独立组件，逐组件搜索完整覆盖；只有唯一覆盖输出建议。搜索到两个解即判定该组件歧义，不能取局部贪心匹配或前两个解的公共行。没有候选的部分保持人工。
- 固定上限为128个正成本单元与来源节点合计、50000步候选/覆盖工作；超限返回null，绝不把截断搜索当唯一解。只在展开详情计算，列表与explorer不计算、不增查询。没有通用求解器、依赖、新缓存/worker/表。
- 明确引用约束来源允许归属的OA；冲突或无法解析的引用不按金额绕过。当前精简OA投影不含足够的外部身份别名，继续只接受canonical引用，不伪造别名。退款缺少逐来源归属证据，非固定成本缺少确定目标，这两类不生成金额建议，保留完整人工编辑/保存链。
- Workbench 的 `exact_amount` / `unique_bank_sum` 是展示对齐，不作为来源证据；不新增子集合搜索、比例算法、hash、表、cache、worker 或 fallback。截图 CASE-AUTO-0016 的金额组合可以作为人工判断线索，但没有原始明确引用时不会自动预填。
- 服务只在 GET 详情计算建议，不把建议送入 policy、统计或持久化。前端草稿初始化优先已保存来源，再读取建议；stale 不复用。已有会话草稿（包括手动删空）不重新初始化。最终保存继续完整校验来源和金额并使用既有事务/版本约束。
- 同一成本单元的项目格和 OA 格使用原生 rowSpan；新增、删除来源后同步更新跨度，删除最后一条仍保留身份与新增入口。不同 OA/成本单元不因项目同名而合并。
- Block 使用四色循环 `#C5D4B8` / `#E8C5A5` / `#DDB9C3` / `#B9CCDF`；数据表格与输入保持白底，颜色不表示财务状态。已删除旧两色选择器、续行空身份格及依赖首个 td 的项目样式，不保留重复路径。
- 上游 Workbench、银行分类与账户页面的写入、DTO 和职责不变；Cost 只消费既有原始引用。read model / worker 合同不变。本轮没有数据库迁移或备份。

## 来源菜单布局与禁用展示（2026-09-10）

- 来源选项高度随内容增长且不参与纵向压缩，菜单限高滚动；银行名称/交易对方/标签可换行，金额保持完整。样式只作用于 CostSourcePicker，不修改公共 ListBox。
- 已用完及同项重复来源保留灰色及真实禁用状态，不显示“已用完／本项已使用”。部分可用、当前行已选中与金额释放后的判断继续由表单拥有；Picker 接收 isSourceDisabled(lineId, sourceId): boolean，输出来源 ID，HTTP 和金额规则不变。
- 删除旧 disabledReason 字符串回调、原因文字节点及 cost-source-option-state 样式；不保留旧属性或兼容分支。

## 当前分配对照与金额提示（2026-09-10）

- `sourceEvidence.ts` 是无 I/O 的展示分组函数：输入单元 ID、流水 ID/类型与草稿 owner/source ID，输出原始索引分组；以已有来源边构建连通组，复杂度 O(单元数+流水数+来源行数)，不读取金额、不推导新的配对。
- `CostSourceEvidence.tsx` 用局部原生语义表格展示该分组：一对一同行，一对多/多对一 rowspan，多对多明确组标题并独立列出两侧事实。每项事实仅出现一次，序号保持来源列表顺序；未选择、无效来源对应的事实、退款与非成本来源均保留。无效输入的错误责任仍在既有校验。
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
- Policy 在完整金额/退款/来源闭合之后按来源有效代码过滤，一次构造集合，不增加逐行 SQL。无 OA 成本取虚拟映射与此范围交集。退款不受范围设置切断。
- 任务详情保留完整事实；列表及计数排除全范围外关系，未知来源组内存在允许支出时保留。`bank_events[].in_project_cost_scope` 由 Policy 输出，前端仅显示“范围外”，不重新实现判断。
- 专用 Drawer 只接收数据与事件。页面拥有 GET/PUT、草稿、超时结果核实和成功后的本页失效；旧分页请求中止、路径重置，保留期间/搜索。不开新队列、缓存或跨页面请求。
- 移除旧 source_pending 正式行生成、分面、导出状态和详情显示分支；保留现有来源 fingerprint、金额校验、事务与正式发布措施。

### 项目成本展示边界（2026-09-11）

`CostStatisticsHierarchy` 只接收各栏的 key、label、amount、selectedKey 与 onSelect，输出选择事件和明细插槽；移除未使用的 description 输入。页面仍拥有查询和选择状态。项目成本根标记限定高度、内部滚动、紧凑样式的作用范围；祖先高度约束仅在该标记存在时生效，不修改 App Shell 或 FinanceTable 公共组件。银行流水两个视角保留公共列表辅助文字与时间 chip。无 API、服务、存储、权限或业务金额 I/O 变化。
