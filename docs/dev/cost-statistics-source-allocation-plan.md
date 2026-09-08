# 成本统计银行来源分配：前后端实施计划

> 执行状态：前后端与Figma Make移植已完成，已提交、推送remote main并部署应用 `cd513a28d`，本地真实PostgreSQL、组件、浏览器与生产链路验证已完成。功能已交付，性能部分达标：独立串行根查询p95约453–470ms，详情约21–22ms；下钻p95约459ms未达到300ms目标，4并发根查询约1,145ms，扩容仍受全量聚合扫描限制。发布、测量条件、测试与清理结果以[实施决策](../modules/cost-statistics/implementation-notes.md)为准；下文保留本次实施范围和决策依据。

日期：2026-09-09。本文保留开发前的设计与复审记录；实际实现与验证状态见顶部执行状态和模块实施决策。

本次按用户要求不使用 GSD；后续执行请求已授权完整开发、提交、推送和部署。当前业务事实以[成本业务口径](../product-specs/cost-tax.md)和[模块边界](../modules/cost-statistics/boundary-io.md)为准；下文中的拟实施描述应与已更新的模块边界和 API 文档一起阅读。

配套交接：[Figma Make UI 设计说明](../modules/cost-statistics/figma-make-design-brief.md)。

执行导航：第3–7节定义业务、架构、存储和接口；第8节性能；第9–10节后端/前端任务；第11–14节旧链、回归和发布；第15节统一执行顺序；第16节完整样例与预期；第17节最终复审。主计划和Make交接各维护一份，不再建立重复实施计划或额外管理平台。

## 1. 目标、范围与必要纠正

### 1.1 目标

| 视角 | 新下钻顺序 |
| --- | --- |
| 按项目 | 项目 → 银行主标签 → 银行子标签 → 成本分配明细 |
| 按流水标签（原按费用类型） | 银行主标签 → 银行子标签 → 成本分配明细 |
| 按银行账户 | 银行账户 → 项目 → 银行主标签 → 银行子标签 → 成本分配明细 |

一条最终分配明细具有：原 OA 成本单元、项目、来源支出流水、分配金额。账户和银行标签从来源流水读取。多对多关系允许用户在一个 OA 成本单元下增加多条分配行，明确来源；同一来源流水可以分给多个 OA 单元，但不能超额或重复使用。

### 1.2 范围

- 后端先确定成本资格、金额闭合、自动/人工边界、存储与读写 API。
- 前端覆盖待分配抽屉、三个成本视角、详情、搜索、分页、导出；只重画抽屉不能交付全部需求。
- 原银行流水 `time|bank_tag` 两视图保留真实收支口径。
- OA、银行导入、关联确认/撤回、银行标签维护、无 OA 规则继续由原 owner 负责。
- 无 OA 已纳入成本的流水直接沿用其来源，不进入 OA 人工拆分。
- 不引入后台 Cost worker、read model、Redis 缓存、事件广播、自动比例分配、金额组合搜索、智能推荐。

### 1.3 不能无条件认可的地方

1. 金额相等不证明来源分配唯一；两个以上正成本单元与两个以上可用支出来源时，不按金额、顺序或名称配对。
2. 「每行填金额、标签、账户」应收敛为「填写金额、选择来源流水，展示其标签和账户」。三个独立选择框可能产生不存在的事实组合。
3. 不能要求人工凭空补出历史付款依据。来源未知是显式业务状态，不是读取旧数据或猜值的兜底。
4. 前端设计无需等待全部后端代码完成；业务规则、DTO 和示例确定后即可交给 Make，避免把设计与开发完全串行。
5. 「不影响其他页面」应通过写入隔离和回归证据落实，不能承诺绝对零缺陷。
6. 删除旧代码不等于删除 OA 的原费用类型、现有审计/版本保护或历史 migration；它们仍有来源展示、其他页面或迁移重放用途。
7. 高性能需要实测。请求次数固定不等于扫描量小，单元测试耗时也不是生产接口耗时。
8. Make生成后先用浏览器验证、修正后再移植是合理顺序，但静态截图不足以验证输入、滚动、弹层和错误状态。每轮应修改明确问题，避免无差别整页重生成；移植App后还必须用浏览器对照实际还原程度。

## 2. 已核实的现状与修复点

| 事实/问题 | 当前位置 | 本次处理 |
| --- | --- | --- |
| 金额相等时直接按 OA 单元出成本，没有银行来源分配 | `cost_statistics_policy.py::_cost_entries` | 金额确认和来源确认分开判定；等额多对多也可进入待分配 |
| 人工分配每单元只能有一个金额，禁止 source 字段 | `cost_statistics_manual_allocation_service.py::_validate_allocations` | 保留单元合计，增加独立来源明细校验 |
| 成本行 `transaction_id` 为空，账户按整组唯一值判定 | `_allocation_entry`、`_resolve_cost_bank_account_label` | 已分配行改用明确来源；待来源行使用独立状态，不能借旧账户逻辑伪装已分配 |
| 月份取整组最后一笔支出时间 | `_append_unit_allocation_entries` | 按用户本轮确认改为每条来源支出的付款日期，见第 3.7 节 |
| 项目成本 Explorer 不加载支出标签 | QueryService `include_cost_row_tags` 调用 | 加载本次成本来源需要的银行有效分类，依旧批量调用 owner |
| 抽屉任务页先全量装载/分类/构造，再在 Python 分页 | `load_manual_allocation_task_snapshot`、`list_tasks` | 任务轻量概览和展开详情分开；不能只把响应切成 50 条 |
| 抽屉组件挂载即以 `page_size=1` 查询全局任务数 | Drawer `useEffect` | 页头复用 Explorer 已计算的计数，删除额外全量读取 |
| 抽屉宽 880px，上方流水证据、下方 OA 项/金额两列 | `CostStatisticsManualAllocationDrawer.tsx`；已现场查看线上 UI | 为 Make 提供真实结构与组件约束；新结构见交接说明 |
| 旧来源矩阵已被 0162 压缩为单元净金额 | migrations `0157`、`0162` | 旧金额保留，不能反推已丢失的 source；不要恢复旧 signed matrix runtime |
| 数据已出现完整三段银行标签路径 | 当前抽屉与 `cost_statistics_bank_tags.py` | 两级导航用 owner 的主/子字段；完整路径保留在详情，不按斜杠自行拆分 |
| 导出仍按 OA 费用分组，前端还有旧 month 分支 | QueryService export；feature `api.ts` | 连同消费方和测试整体收口，不能只改 Explorer |

全仓引用扫描还命中：`server.py` 接线、`tests/postgres_test_utils.py`、`tests/test_postgres_migrations.py`、`web/src/test/apiMock.ts`、API 文档及现有验证矩阵。需要逐项检查，不扩展修改其他业务模块。

部分仓库总览文档仍含已退役 read model 描述。本次依据当前成本/银行模块代码和正式 direct-read 边界执行，不恢复旧 worker，也不顺带重写无关文档。

## 3. 业务合同

### 3.1 成本资格与单元

- 只读取 active 正式关系；任一 OA 未完成或成员不完整，沿用整组不纳入成本的现有规则，且不能落入无 OA 成本。
- 支付申请整单为一个成本单元；日常报销按 canonical `expense_items` 形成单元。
- 单元以既有稳定 `unit_id` 标识，保留原项目归属。不能按项目名、申请人或标签创建新的 OA 对应关系。
- 原 OA 金额与「最终计入成本金额」分开。当前 `O != N` 允许人工决定各单元成本；本次不新增「成本不得超过 OA 原金额」限制。
- `O = N` 且没有人工金额差异时，单元目标为原 OA 单元金额，不允许仅为凑某个来源擅自改动目标。
- 服务端必须逐单元核对当前canonical目标，不能把请求里的`allocations`直接当成权威目标。原A600/B400、银行各500，即使提交A500/B500后所有请求内合计都平，仍须拒绝。`O != N`继续沿用人工决定最终成本的原规则，不新增OA原额上限。
- 所有金额使用既有两位小数字符串合同、后端 Decimal/分，不能使用浮点累加。零值与未填分开；成本来源行必须大于零，整单元明确不计成本可为零并显式确认。

### 3.2 两边金额闭合，补齐退款和非成本来源

保留现有关系总规则：

```text
B = 关系内支出原额合计
R = 同关系内明确「付错退款」收入合计
N = B - R
C = 各 OA 单元最终成本之和
X = 明确不计入成本的金额
C + X = N
```

为了明确到银行账户/标签，增加来源层明细：

- `cost_lines`：哪个 OA 单元使用哪笔支出、使用多少净成本。
- `refund_links`：每笔明确退款冲减哪笔原支出、冲减多少；不是负成本行。
- `non_cost_lines`：每笔支出有多少净额明确不计成本。

对每笔支出 `b`、每笔退款 `r`、每个单元 `u`：

```text
sum(cost_lines[bank=b].amount)
  + sum(refund_links[bank=b].amount)
  + sum(non_cost_lines[bank=b].amount) = bank[b].gross_amount

sum(refund_links[refund=r].amount) = refund[r].amount
sum(cost_lines[unit=u].amount) = unit_allocations[u].amount
sum(non_cost_lines.amount) = X
```

这三类明细是逐来源核对的必要输入，不做通用复式记账引擎。没有退款或非成本时相应数组为空、UI 不展开相应区域。退款来源只有一个时可确定性带出；多来源不能按比例冲减或根据退款账户反推原付款账户。

`N = 0` 保持无成本，不制造零成本明细；`N < 0` 保持明确完整性错误。普通收入不进入退款分配。每笔来源必须属于当前关系，且方向合法；不得引用别组流水。保持既有重复 active owner 检查。

零净成本在完成资格、成员/重复归属和总额完整性检查后直接维持无成本结果，不为本次成本页面强制建立没有成本可分的退款矩阵。来源双边闭合要求适用于需要保存来源决定的有效任务，不将`N=0`扩成新人工流程；原银行收支仍正常展示。

### 3.3 自动分配的充分条件

按事实而非凑数自动决定：

1. 先确认各 OA 单元成本目标；金额未知就进入人工分配。
2. 再确认退款和非成本的支出归属，得到每笔支出剩余可计成本金额。
3. 若只有一个可用支出来源，各已知单元金额直接归给该来源。
4. 若只有一个正成本单元，各已确认可用来源金额全部归给该单元。
5. 两边都存在多个正金额对象时，默认人工。即使金额恰好相等、标签/账户相同，也不声称知道逐笔来源。
6. 有已经保存且当前有效的人工来源明细，优先使用该明确事实；不因现在存在另一种自动分法改写人的决定。

不新增匹配算法、子集搜索、笛卡尔积矩阵或比例建议。自动结果请求内计算即可，不为其创建持久化任务记录。

### 3.4 待分配、已分配与事实缺失

保留任务 API `pending|allocated` 选择，`stale` 继续显示在待分配内。拟定 `pending_reasons` 枚举：`amount_required`（金额待定）、`source_required`（来源待定）、`allocation_stale`（分配失效）、`bank_tag_missing`、`bank_account_missing`、`source_date_missing`；允许多个原因并存。类型与测试使用同一有限枚举，不以中文显示文字作为逻辑值。

- 金额已知、来源未知：每个单元形成一条显式 `allocation_state=source_pending` 展示行，计入「全部时间」的已确认总成本，但不伪造 transaction/account/tag/date。主/子/账户分面均保留待分配分组；指定年月时将无法确定月份的金额单列提示，不计入所选期间合计，三个视角遵循相同规则。
- 金额未知：不把 OA 原额或银行原额伪装成本；列入待分配任务，汇总单独说明尚有金额未确定的关系。
- 来源明细已保存、银行标签、账户或付款日期缺失：可以保存真实来源关系，不把缺失值编成真实事实。成本行准确显示已有维度；任务原因指向银行信息维护。日期缺失同样不能进入指定月份合计。标签补齐后下一次 GET 可复用已保存来源决定。账户或付款日期变化仍遵守既有 fingerprint 保护，可能使原决定失效，需要重新确认；不为省事删除这一保护。
- 稳定来源记录失效：不沿用旧金额/来源生成 fresh 结果。保留历史记录用于审计与用户查看；按当前事实重新确定金额能否保留，不能无条件从 stale 记录取值。
- 空白草稿只在当前抽屉会话中保留，关闭/切任务丢失前复用现有确认。第一版不新增服务器草稿表或自动保存服务。
- 用户可删除尚未提交的分配行；已保存整组修改通过一次 PUT 原子替换，不新增逐行 DELETE 接口。

已持久保存与所有问题已处理必须分开：任务顶层`allocations/source_allocations/non_cost_amount/non_cost_reason`只承载当前验证有效的决定，stale旧决定通过既有审计保留，不能混入当前有效字段。Drawer按有效决定回填，即使任务仍pending；删除`status === allocated`才回填的旧条件。历史只有金额时保留目标金额，来源已保存但标签缺失时回填完整行。

保存服务用同一纯规则重新计算响应的`status/pending_reasons`，不硬编码allocated。资料仍缺失时显示“分配已保存，银行信息待完善”，保留pending任务；只有返回状态确实改变才移动列表项/调整计数。刷新不覆盖其它任务脏草稿；同一任务版本变化时保留本地输入供核对，不悄悄重置正在填写的表格。

待分配分组必须有独立状态/key，不能用一个可能与真实项目/标签同名的中文字符串充当身份。已知「未标记」与「尚未确定来自哪笔流水」是不同状态。

### 3.5 标签和账户事实

- source 选择只限当前正式关系内真实支出流水。
- tag/account 不作为分配写请求中的自由字段，服务端不信任客户端复制的文案。
- 复用 `effective_category_projection_rows(...)` 与 `BankAccountResolver`；不复制银行分类 SQL，不向银行页面 API 发 N+1 请求。
- 在canonical repository入口将owner公开的`effective_category_code/label/primary_label/sub_label/label_path`明确映射成成本字段，policy和DTO只读这一种标准形状。清理`cost_statistics_bank_tags.py::bank_tag_context_from_row`中的多组字段轮流尝试、从显示文案补出主子标签等旧猜测逻辑；不把它继续用于新分配行。
- 「owner明确返回未分类」是合法未标记状态；「已读取的有效银行ID在应完整返回的分类投影中缺整条记录」是完整性错误，不能用空字典掩盖。合法无子级标签遵循owner的层级定义，不自行复制主标签生成子标签。Local测试适配器显式产出同一标准形状，不让生产reader兼容测试私有字段。
- 主/子标签按 owner 的明确字段导航；保留完整 `bank_tag_label_path` 和稳定 code。真实三段路径不增加第三层导航，也不能丢掉证据中的第三段。
- 同一主/子组合可包含多个叶子 code，按该组合汇总但每行仍保留来源 code。子标签必须与主标签绑定筛选，不能全局按同名子标签混组。
- source mapping 不持久化一份会与银行明细分叉的标签字典。普通标签文案变化下一次读取当前文案；现有 relation version/fingerprint 已造成的失效保护保留，不放宽。
- 多账户的实际分配金额直接来自来源行，删除已分配行上的整组账户推断。账户缺失保留真实缺失状态。
- 本次沿用当前成本模块的账户显示与分组口径，不自行发明新的账户 hash/key；账户身份有重名或映射冲突时先向银行 owner 核实，不静默合并不同账户作为来源依据。

### 3.6 三视角、明细、导出的一致性

- 先构建一次成本事实集合，按scope/query形成基础集合；各栏只使用已选上游条件计算分面，完整路径只用于末级明细，最后分页。不能先过滤到叶子再生成每一栏。
- 三个根视角使用完全相同事实人口和金额。
- 分配明细与原成本单元分别计数；银行流水按 ID 去重计数，不把拆分行数当流水笔数。
- 已分配行身份是关系 + 单元 + 支出来源的稳定组合。后端拒绝同一组合重复提交；UI提示用户把金额填写到已有来源行，不静默合并或自动改金额。使用可编码的稳定元组，不新增hash。
- 详情先定位一条分配行，展示该行金额、所属 OA 单元总额、来源流水原额和关系核对；不得在多行重复展示原额并当作可加总成本。
- 导出同时提供成本金额、项目、银行账户、主/子标签、完整标签路径、来源付款时间、原 OA 信息和分配状态。旧 OA 费用类型可保留为来源列，不能继续充当成本分组键。
- CSV/XLSX 数值不由浏览器重算。导出上限仍为 20,000 明细行，超限明确报错，不截断伪成功。

| 视角 | 第1栏 | 第2栏 | 第3栏 | 第4栏 | 第5栏 |
| --- | --- | --- | --- | --- | --- |
| 按项目 | 基础集合所有项目 | 所选项目内所有主标签 | 所选项目+主标签内所有子标签 | 完整项目/主子路径明细 | — |
| 按流水标签 | 基础集合所有主标签 | 所选主标签内所有子标签 | 完整主子路径明细 | — | — |
| 按银行账户 | 基础集合所有账户 | 所选账户内所有项目 | 所选账户+项目内所有主标签 | 所选账户+项目+主标签内所有子标签 | 完整路径明细 |

选中子标签后，其同级子标签和上游其它项目/账户仍可切换。必要上游未选择时，下游为空并提示选择。待来源/缺失维度分组遵循同一上游过滤规则，不让状态参数反过来清空上游兄弟项；三个明确视角分支即可，不引入通用分面引擎。

保留现有页头`summary`的期间/搜索基础集合口径，不随末级选项缩水；当前路径金额在分面和明细上下文展示，`row_count`为当前路径分页前数量。导出按所选范围/路径计算合计，不能把页头根总额当成路径导出合计。

### 3.7 日期口径（用户已确认按来源付款日期）

2026-09-09 用户确认：同一 OA 成本单元 600 元，8 月建行付 350 元、9 月民生付 250 元，拆为至少两条成本明细，分别进入 8 月和 9 月。以此替代本轮早先「沿用整组最后付款月」的建议。

| 明细 | 原 OA 单元 | 来源 | 成本日期 | 成本金额 |
| --- | --- | --- | --- | --- |
| 1 | 同一单元 | 建行支出流水 A | A 的实际付款日期（8 月） | 350.00 |
| 2 | 同一单元 | 民生支出流水 B | B 的实际付款日期（9 月） | 250.00 |

实施规则：

1. 已分配行 `occurred_at` 取该来源流水的 canonical 付款日期，明细中的 `occurred_at` 保留来源真实付款日期，来源证据继续用 `trade_time`，不再新增同值日期别名；不新增可手填的成本月份。不再取整组最后支出或 OA 审批日期。使用银行 owner 既有日期归一化和应用时区，不自行按 UTC 截月份。
2. 一个来源分给多个 OA 单元时，其各条分配行使用同一来源日期；同一 OA 单元可以跨月。金额、账户、标签和月份均定位到同一来源 ID。
3. 必须先读取候选关系的完整成员、处理退款和非成本、构建分配行，再按分配行日期筛选。可以用月份支出查候选关系，但不能只读取当月部分来源后计算关系余额；初次 GET、`include_statistics=false`、导出三个入口结果一致。
4. 金额已知但来源或日期未定：全部时间合计包含该金额，显示「月份待确定」；指定年月合计不包含它，同时单列「仍有金额无法确定月份」及进入待分配的入口。这条提示说明全局未定金额，不冒称是该月金额。可通过相同项目/标签条件缩小已知维度；未知维度不猜值匹配。
5. 原 OA 合计仍为 600 元，全时间总成本仍为 600 元；月度加总与全时间金额之间的差额，必须能由「月份待确定」金额解释。来源都确认后，各期加总必须等于全时间合计。
6. 保持当前付错退款的净成本语义：退款先明确冲减原支出，再将该支出的净成本归入原付款月份。跨月退款可能调整原月份成本，不新增退款发生月的负成本行；银行流水视角仍如实在退款发生日展示实际收入。这是本次成本统计口径，不能声称它等同于各月银行净现金流。
7. 旧数据完成来源分配后，原本集中在最后付款月的成本会分散到真实付款月份。这是本次明确的行为变化；迁移验证按月列出变化和未定月份金额，不能要求所有历史月报数字不变，也不能静默套用旧月份。

普通收入冲减成本、跨币种换算或新的退款业务规则不在本次范围；沿用既有准入规则。若当前关联事实本身不足以解释退款来源，继续人工处理，不能由跨月规则反推金额归属。

## 4. 模块架构和 I/O

```text
CostStatisticsPage / ManualAllocationDrawer
  -> 成本 API client
  -> CostStatisticsApiRoutes（鉴权、解析、HTTP）
       -> CostStatisticsQueryService（读取/导出 DTO）
       -> CostStatisticsManualAllocationService（事务保存）
          -> canonical repository（同快照事实、定向读取/锁）
          -> CostStatisticsPolicy + 小型纯来源分配模块（同一业务规则）
          -> manual allocation repository（本模块唯一写表）
          -> existing audit repository（同事务）

canonical repository
  -> app.bank_transactions / app.oa_applications / active relations / settings
  -> 银行 owner 的批量 effective-category port
```

| 边界 | 输入 | 输出 | 不允许 |
| --- | --- | --- | --- |
| Route | HTTP、真实 session、query/body | 200/400/403/404/409、文件 | 金额算法、SQL、body actor 兜底 |
| Read repository | scope、case IDs、指定事实列 | 单个一致快照、轻量概览或目标详情 | 页面 payload、逐行 I/O、跨模块写 |
| 来源分配纯模块（拟新增一文件） | OA 单元、银行来源、金额决定、来源决定 | 自动/人工状态、金额校验、分配行 | DB、HTTP、Application、全局状态 |
| CostStatisticsPolicy | canonical snapshot + 纯分配结果 | 统一成本人口、分面、详情 | 第二套来源分配逻辑 |
| Save service | 指定 repository、来源分配函数、actor | 原子决定、version、审计 | ORM/SQL 细节、自由标签修正 |
| Allocation repository | 经过校验的同组完整决定、CAS version | 一行持久记录 | 业务标签推断、写 bank/OA/relation |
| Frontend | API DTO、用户输入 | 草稿、提示、一次提交 | 自动凑数、生产 DB、跨页通知 |

拟新增 `services/cost_statistics_source_allocation.py`，只容纳紧密相关的纯金额/来源规则。理由：现有 policy 超过 2,000 行，读取与写入都需要相同规则；不再叠一个通用 service/facade/factory。其余主要在现有文件内修改。

## 5. 存储、迁移与历史数据

### 5.1 最小存储方案

复用 `app.cost_statistics_manual_allocations`，保留现有 `unit_allocations`、关系总金额、version、source_fingerprint、actor/time；仅拟增加一个可空 JSONB 列 `source_allocations`：

```json
{
  "cost_lines": [
    {"unit_id": "既有单元ID", "bank_transaction_id": "既有支出ID", "amount": "600.00"}
  ],
  "refund_links": [
    {"refund_transaction_id": "既有退款ID", "bank_transaction_id": "既有支出ID", "amount": "35.00"}
  ],
  "non_cost_lines": [
    {"bank_transaction_id": "既有支出ID", "amount": "15.00"}
  ]
}
```

上例仅说明字段，不是一份金额已闭合的完整业务请求。

- `NULL`：尚无来源决定；不等于已完成的空分配。
- 非 NULL：必须满足完整 shape 和金额合同。JSON 错误不吞掉、不忽略非法行。
- `unit_allocations` 是每单元最终成本合计；来源明细是其逐银行分解。保存时强制两者相等，二者职责不同，不允许独立更新。
- 不新增 task/status/cache 表，不把 UI 临时行 ID 存入数据库；不保存客户端标签/账户显示快照作为新事实源。
- 现有 record mapper 中对缺失/坏字段的宽松默认要在新来源边界明确区分 NULL、合法值和损坏值。
- migration 使用实施时的下一可用编号，不能现在猜编号，也不修改 0157/0162 历史文件。

### 5.2 历史决定

- 新列默认 NULL，原单元金额、X、原因、审计、版本不改写；不删除旧决定。
- 旧决定仍通过现有来源有效性检查；有效金额可保留在待来源行里，用户只补来源。
- 符合严格自动条件的关系可在请求内自动确定来源，无需批量写入旧记录。
- 不能从 0162 丢失的明细、raw_payload、旧导出或过期审计随意恢复来源；不能按比例分配历史数据。
- 旧值成为新域的「金额已知、来源未定」输入，不保留第二套旧成本构建或旧 API 写格式。

### 5.3 回滚和备份

- 采用追加列迁移，不需要为本次默认建立全库备份或影子数据库。
- 新旧部署不得混用写请求合同；迁移与 API/前端切换纳入一次正常发布安排，旧浏览器遇到不支持字段明确提示刷新，不做隐式兼容。
- 回滚代码时保留新列和分配事实；原 `unit_allocations` 保持合法，旧版本可恢复原成本展示能力，但不宣称仍提供新来源精度。修复后前进发布。
- 不 DROP 主数据库，不恢复旧全库备份覆盖上线后的新事实，不给 runtime 增加 DELETE 权限。
- 若正式发布的现有流程必须产生临时备份，只记录本任务实际创建的确切路径/名称；成功验证、确认不再用于本次回滚后仅清理这些临时副本。失败未完成时不能先删唯一恢复材料；长期既有备份、主库和审计不属于清理对象。
- 本轮未连接主库执行 SQL、未创建任何数据库备份。

## 6. 事务、并发和现有安全措施

1. 保留真实 session、现有页面权限和审计；不新增权限层级。
2. 保留现有 `expected_version` CAS 与 `source_fingerprint` 检查，不新增 hash 家族或冻结合同。
3. 保存只处理一个关系。使用既有 relation owner 的成员/关系锁顺序，取得当前 active 事实后，在同一事务读取金额与来源、校验、保存 allocation 和 audit。
4. 当前代码只对关系 `FOR UPDATE`，银行/OA 本体查询不加锁。B2 必须补充真实 PostgreSQL 并发测试，验证与关联撤回、OA 更新、银行事实变化同发生时的行为。需要锁源行时，仅锁本组具体 canonical 行并遵循现有 owner 顺序，不引入全局锁或改变 owner 写流程。不要在持有关系锁后反向获取银行分类 writer 的锁，造成死锁。
5. 读取仍为 `REPEATABLE READ READ ONLY`，writer 采用符合现有连接/UoW 的一致性策略；不套只读事务做写入。
6. CAS 冲突、来源不属于关系、源金额变化、重复来源超额均明确失败；失败不留下半条来源记录或 success audit。
7. 网络超时后不盲目重复 PUT。前端重新 GET 当前关系，将返回 version 和已保存规范化决定与本次提交比较；已保存则展示成功，否则保留草稿与冲突信息。利用现有版本和记录即可，不新增幂等 hash。
8. 新来源映射以银行 ID 为依据，标签显示按当前事实读取。若银行标签变化影响「付错退款」准入或现有 relation version，则下一次读取重新验证金额/有效性；不能只做显示换字。
9. `server.py` 只接线。移除 cost route 中未配置 session 时从 body/default actor 取身份的旧测试便利分支，测试改为显式注入认证会话；不重构全站权限系统。
10. 同事务审计payload增加校验后的完整`source_allocations`和保存version，不仅记录单元总额。每次整组替换后仍能从原有审计追溯此前来源决定，不新增历史表/平台，不记录多余银行原文。

B2 的现有复用入口已定位：`PostgresWorkbenchRelationRepository.acquire_relation_member_locks(row_ids, row_types=..., case_ids=...)` 按稳定成员顺序获取事务锁，银行分类闭环也使用它。Cost 通过显式注入的事务内 repository port 调用，不复制其 advisory key 算法；既有实现内部使用的 hash 不属于本次新增 hash。

复审发现的并发注意点：owner 的 `lock_canonical_relation_members(...)` 使用 `FOR KEY SHARE`，它不能替代对金额/日期更新的保护。实施时先用两个真实 PG 连接复现「保存分配与源金额/OA更新并发」，再在 Cost repository 内选择与实际 writer 顺序兼容的源行锁；获锁后必须重新读取成员和金额，成员变化直接 409。不能把只检查成员存在当作事实未变化，不能在未验证顺序前把更强锁铺到共享 owner。这个局部事务修复是 B2 的交付，不作为先行全仓重构或新增审批流程。

## 7. API 详细计划

以下字段为拟新增/变更合同，不能当作现有 API 直接调用。

### 7.1 人工分配列表、详情、保存

- `GET /api/cost-statistics/manual-allocations`：保留 `status/query/cursor/page_size`，返回轻量任务概览及同快照 counts。列表不携带每个任务的完整流水/分配矩阵。
- 拟新增同资源详情 `GET /api/cost-statistics/manual-allocations/{case_id}`：仅展开任务时读取；返回 units、bank events、来源分配、金额余额、待处理原因、version/fingerprint/can_save。
- `PUT /api/cost-statistics/manual-allocations/{case_id}`：复用现有整组原子保存。

拟定保存请求：

```json
{
  "relation_case_id": "当前case",
  "expected_version": 0,
  "source_fingerprint": "当前接口返回的既有指纹",
  "allocations": [{"unit_id": "当前unit", "amount": "600.00"}],
  "non_cost_amount": "0.00",
  "non_cost_reason": "",
  "source_allocations": {
    "cost_lines": [{"unit_id": "当前unit", "bank_transaction_id": "当前bank", "amount": "600.00"}],
    "refund_links": [],
    "non_cost_lines": []
  }
}
```

前端从输入行计算每单元合计构造 `allocations`，不需要用户把同一金额再填一次；后端独立复算并校验。所有单元必须被显式覆盖，零成本单元明确提交 0.00，不能把漏填理解成零。缺少来源对象的旧写请求明确拒绝；NULL 只用于历史金额记录/明确未决定状态，不作为新完整保存的默认值。

`O=N`时，前端显示只读单元目标，服务端另与canonical目标逐项比较，不能只比较请求内部的单元合计与来源合计。

bank event DTO 增加来源选择所需的账户显示、稳定 ID、effective tag code/主子字段/完整路径、原额、已退款冲减、非成本及本次剩余金额。剩余金额由当前关系草稿计算，本地交互计算仅做提示，服务端仍权威验证。

保存成功返回当前任务决定、version、状态/原因；不返回刷新 job。失败保留现有 error/message，加有界的行/单元/source 字段错误供定位：非法输入 400；无权限 403；读取不存在 404；关系撤回、来源/版本变化 409。body actor/account/tag 字段拒绝。

### 7.2 Explorer 与导出

- 计划用 `cost_tag` 取代 OA 费用分组 `expense_type` view；`bank_tag` 保留银行真实流水分析，不混用。
- `project`、`cost_tag`、`bank_account` 都接受现有 `bank_tag_primary_label`、`bank_tag_sub_label` 成对下钻语义；project/account 前置参数依视角明确校验。
- 删除成本 Explorer/export 的 OA `expense_type` 筛选/分面/排序分支；OA 费用类型留在来源详情字段里。旧值明确拒绝，不重定向到不同业务含义的新 view。
- 继续固定 `summary/statistics/facets/rows/row_count/next_cursor` 包络，增加分配状态与计数字段；facets 始终以有名称的集合返回（projects、bank_accounts、bank_tag_primary、bank_tag_sub），不再用仅 primary/secondary 两级中间模型表达四级导航。
- 拟用 `allocation_state=source_pending` 选择来源待定的分面；禁止依靠将“待分配”作为真实 tag 参数传入。已映射但银行维度缺失通过 `missing_dimension=bank_account|bank_tag_primary|bank_tag_sub|source_date` 精确筛选，不与来源待定混用；相关参数进入 cursor 条件和导出请求。
- cursor 绑定全部视角/范围/搜索/层级参数；排序使用成本时间 + 稳定分配身份，不使用数组下标或临时 UI ID。用户跨请求写入后重置当前分页并重新读，不承诺跨多个 GET 的冻结快照。
- null日期在全部时间中排末尾，以稳定身份继续分页；不将null字符串化或伪造日期。cursor编码与比较使用同一排序元组。复用现有编码，给改变身份语义的成本cursor增加普通格式版本以拒绝旧cursor，前端明确重置分页；原银行流水cursor不改，不保留旧成本cursor兼容分支。
- `allocations/{id}` 详情对应分配行；待来源行有明确 kind，无银行 ID，不请求不存在的流水。
- OA行继续使用`row_kind=oa_allocation`，另用`allocation_state=source_resolved|source_pending`区分来源状态；账户/标签/日期是否缺失单独表达，不能把“来源已知但标签空”误判为来源未分配。新成本DTO对未知`transaction_id/occurred_at`明确返回null并同步TypeScript类型，不能用空字符串假装合法ID或日期；原银行流水DTO不受这项变更影响。
- 导出预览/下载同步接入 cost_tag、主子标签、状态筛选和分配明细。清除前端孤立 `view=month` 等无后端消费分支前完成全仓扫描。
- 原 `time|bank_tag` 查询、详情、导出响应及方向净额规则保持回归保护。
- 导出只要存在任意起止年月/日期限制，就排除未知日期行并提示未定月份金额，不能仅传`end_date`时把空日期纳入。无时间限制的原始成本明细导出包含未知日期行及状态；月/年汇总单列“月份待确定”，不假造日期或静默丢金额。

### 7.3 任务读取和金额反馈字段

保持 wire JSON 的 snake_case 和现有 frontend mapper 的 camelCase，不在组件直接处理数据库 JSON。下表为待实现接口字段；名称不代表已经存在。

| 对象 | 字段与语义 |
| --- | --- |
| 任务列表包络 | 沿用 `items/row_count/counts/next_cursor`；`row_count`是当前status/query命中的总任务数；`counts.pending/allocated`保留现有全局任务计数，不被query或所选status缩小，pending包含stale |
| 轻量任务项 | `relation_case_id/relation_version/status/pending_reasons`，项目名集合、OA 合计/净支出/已确认成本、单元数/来源数、`version/updated_at/can_save`；不含完整 `units/bank_events/source_allocations` |
| 任务详情 | 沿用现有完整 task 字段，增加 `pending_reasons`、`source_allocations`、每来源账户/有效标签/日期和核对值；列表展开只取这一组 |
| Explorer 金额反馈 | 在现有 `allocation_quality` 中增加 `undated_cost_amount/undated_cost_unit_count`；当前查询已知维度内、尚不能定位年月的金额和单元数，独立于期间 `summary.total_amount`，不能再相加成“当月成本” |
| 行校验错误 | `field_errors` 中每项含 `path/code/message`，例如 `source_allocations.cost_lines[1].amount`，code 用有限业务值如 `invalid_amount/source_overallocated/unit_total_mismatch/duplicate_source_line`；索引只用于本次输入定位，不是持久身份 |

新的标签分面必须累计分配成本金额；不能直接复用银行原始流水分面的 gross expense/net 计算。两种视角可复用显示组件，但 DTO 金额语义和查询入口保持明确。

对成本行按 `(unit_id, bank_transaction_id)`、退款按 `(refund_transaction_id, bank_transaction_id)`、非成本按 `bank_transaction_id` 拒绝重复项；ID、方向、归属、金额格式和总量均由服务端校验。输入顺序不影响金额结果。JSON 对象禁止未知字段，明确空数组的合法条件，不丢弃不认识的行后继续保存。

## 8. 性能设计与测量

### 8.1 必须实施的低成本优化

- 分配使用稀疏用户行；CPU 遍历为 O(单元数 + 来源数 + 分配行数)，禁止创建 OA×流水全部组合。
- 来源按 ID 建索引，金额以整数分/Decimal 累计，不能对每行扫描整个来源列表。
- 概览 query 按 scope/关联 IDs 下推，只取成本需要的字段；不加载附件、发票树、raw 业务大 payload 后丢弃。
- 任务列表：同一 snapshot 批量读取轻量判定事实，使用同一纯 policy 判定后分页；只对本页任务水合展示元数据，展开后单独读取具体关系详情。不能先 SQL 分页再过滤 pending，否则会漏任务。
- exact 全局待分配数量本质上需要评估候选关系；第一版用紧凑事实批量计算，不宣称它天然 O(page_size)。不另持久化派生状态表，也不复制一套 SQL 金额业务算法。
- 三个成本视角共用一次事实构建；实际来源支出与退款标签分别按必要 IDs 去重后一次批量 owner 查询。
- 删除 Drawer mount 的额外 count 请求：初次 Explorer 同一完整统计读取返回 pending count；打开抽屉再读取实时列表。切换两个银行流水视角不读取人工分配。
- 若首先进入银行流水视角且尚未读取任务数量，显示“待分配”入口，不把未知数量显示为0；打开抽屉后使用列表返回的counts。保存后按返回任务状态更新当前组，不能固定把待分配数减1，因为信息缺失的组可能仍然pending。
- 输入、增删行、展开本地选择不发保存或全局查询请求；来源候选从本关系详情取得，本地搜索。
- 保存成功只更新当前任务，并重新读取当前成本页面一次；不通知其他页面、不触发全站刷新、不自动预取每个任务详情。
- 明细固定 20 行，任务列表沿用 50 上限、显式加载更多；无业务依据不新增任意“最多几个分配行”限制，复用现有 HTTP body/statement/connection timeout 资源边界。

### 8.2 可测目标，不新增性能 gate

建议性能目标：代表性生产规模、热连接条件下，Explorer 初次 p95 ≤ 500ms，下钻/任务展开 p95 ≤ 300ms，普通单关系保存 p95 ≤ 500ms（服务端耗时）。这是待实测目标，不是本轮已达到的结论，也不写成新的 CI baseline/gate。

记录真实当前规模及 10 倍合成规模；每场景至少 30 次、并发 1/4/8，分别报告冷启动一次、p50/p95/max、SQL 数、扫描/返回行、payload 字节和总 HTTP 耗时。测首次列表、末页、搜索、等额 N:M、含退款、100 条以上用户分配行、三个视角与导出上限。

合成数据和并发压力矩阵只在隔离测试环境运行。生产仅有限只读抽样，不在主库生成压测数据或执行并发压力矩阵。

性能不达标先用 `EXPLAIN (ANALYZE, BUFFERS)` 找到具体 SQL/扫描问题，再做投影列/谓词/既有索引优化。新增索引须对应已测查询；不默认加缓存、worker或状态镜像。生产只读 probe 使用现有 token wrapper，禁止输出凭据。

## 9. 后端实施顺序（优先）

| 步骤 | 具体交付 | 文件/责任 | 完成证据 |
| --- | --- | --- | --- |
| B1 口径与 I/O | 将已确认来源付款日期及本文 DTO 落入类型/文档；补退款/非成本来源、任务状态示例 | 本计划 + Cost boundary/API docs | 正常/歧义/跨月/退款/历史 NULL/失效示例均能按同一规则解释；不是建立冻结文件 |
| B2 最小存储与事务 | 新列 migration、严格 mapper、CAS 保存、同事务 audit、来源锁与并发保护 | 现有 manual repository/service + 下一 migration；测试 helpers | 真实 PG 新库/升级库、并发冲突、失败回滚通过 |
| B3 纯分配规则 | 稀疏来源校验、确定性自动分配、未确定状态、历史金额保留 | 新 `cost_statistics_source_allocation.py`；替换 policy 对应段 | 单元/来源双边闭合，歧义不猜，零/负/退款/非成本与旧记录回归 |
| B4 查询与任务 API | 概览/详情拆分，支出标签批量读取；等额 N:M 纳入任务 | canonical repository、query/manual service、routes | 请求内单快照、列表搜索/分页不漏、展开定向读取、权限/DTO通过 |
| B5 三视角/详情/导出 | cost_tag 替换、完整分面、稳定身份、来源付款月份、pending/未定月份金额归组 | policy、query service、routes、受影响 audit/probe读取适配 | 三根相等、每级闭合、8月350/9月250、跨期来源完整读取、详情和导出一致、原流水视角不变 |
| B6 删除旧链并验证 | 按第 11 节移除旧构建/调用/DTO/独占测试；更新接线 | 限 Cost 文件与真实消费方 | 无旧生产调用、无 OA/Bank/Relation 写入、副作用隔离与性能测量 |

实施为小步提交，B2/B3 可在同一开发批次，但不能只合并新代码而留下旧逻辑继续被主链调用。没有用户要求的代码执行授权前停留于本计划。

## 10. 前端与 Figma Make 顺序

2026-09-09 按用户补充要求调整：以Figma Make生成的、实际浏览器验证合格的UI为移植视觉依据；移植时尽量还原，不自行换成另一版布局。本节中的「验证后进入下一步」是用户要求的开发顺序，不新增审批节点或CI gate。

```text
后端规则/DTO + 当前UI参考
  → Make生成可运行UI
  → 浏览器视觉与交互验证
      有问题 → 反馈Make定点修改 → 浏览器复验
  → 记录采用的Make版本、截图和视觉参数
  → 移植展示组件，接入App数据与交互
  → App浏览器与Make同条件对照
      移植偏差 → 修App局部实现 → 复验
      设计遗漏 → 回Make修正 → 同步移植并复验
  → 性能/业务回归、旧链清理确认、交付
```

| 步骤 | 具体交付 | 实施范围与完成方式 |
| --- | --- | --- |
| F1 设计输入 | B1的DTO、当前抽屉/三视角截图、App组件约束和演示数据 | 更新Make brief；规则/DTO确定即可设计，不等待整个后端发布；这一步不移植UI |
| F2 Make生成 | 可打开、可操作的右侧抽屉；配套4/3/5栏导航与关键状态 | 以现有平台样式生成演示UI；不改变业务口径、不调用生产API；记录真实预览入口 |
| F3 浏览器验证与迭代 | 操作新增/删除/输入/来源选择/滚动/保存/错误状态，检查窄屏和五栏 | 按brief第6节检查；每轮反馈位置、触发方式和预期，Make修改后验证受影响及相邻状态；问题未解决则继续，不跳到移植 |
| F4 移植依据整理 | Make链接/版本说明、关键截图、可取得源码与实际视觉参数 | 记录抽屉宽度、间距、字号、颜色、行高、滚动/弹层行为；普通任务记录即可，不新增冻结合同、hash或截图baseline |
| F5 展示层移植 | 按Make还原布局、控件、来源卡和状态，替换成本旧展示及冲突样式 | 复用AppDrawer的width/className/footer/headerActions、HeroUI、FinanceTable；必要时拆局部task editor；不整体复制Make工程 |
| F6 App数据与交互 | DTO mapper、独立草稿、稳定行key、金额提示、AbortController、保存/冲突重读；三个视角/详情/导出 | 仅Cost client访问后端；移除旧单金额draft/费用导航；演示数据只留设计和测试，不进入运行时兜底 |
| F7 App还原复验 | 相同浏览器、窗口、缩放、演示数据和状态下对照Make，再验证真实API | 修正布局/字体/间距/控件/滚动偏差；修App实现问题不必重生成Make，设计遗漏回Make后同步更新 |
| F8 联调与交付 | 分配→保存→三视角→详情/导出；接口失败/并发、其他页面回归、真实交互耗时 | 现有组件测试/Playwright/PG集成；核对旧链和局部旧CSS删除，记录效果、性能及剩余差异 |

宽屏显示四/三/五栏；较窄屏通过保留已选路径、折叠上游导航逐级下钻。不能为五栏强行压缩明细到不可读；继续完整显示长项目名和标签路径。金额两位小数、无千分位遵守现有应用约定。

### 10.1 高还原的可执行约定

- 以F3验证后的Make实际渲染作为视觉参照，保留信息结构、尺寸比例、字体层级、间距、色彩、边框、圆角和状态表现。复用App组件不能成为随意改变外观的理由。
- 将Make视觉参数映射到现有变量/组件参数，缺少的样式仅在成本模块命名空间补充。不覆盖通用`.finance-drawer`、`button`、`table`或全站字体来“让截图一样”，不靠重复覆盖压住旧CSS。
- 浏览器至少检查常用桌面1440×900、大屏1920×1080、窄窗口1024×768（CSS像素）；主尺寸跑完整代表场景，其余尺寸聚焦长文本、来源弹层和五栏，避免全部状态乘以全部尺寸。
- 同条件指浏览器、缩放、字体加载、内容区域尺寸、数据和展开/选中状态一致。编辑器边框不算App内容；不能拿不同宽度和数据的截图证明还原程度。
- 不承诺跨系统字体抗锯齿逐像素相同，不以“95%还原”代替证据；必须消除可见错位、信息遗漏、截断和行为偏差。
- 若Make设计与可访问性、已确认业务规则或实测性能冲突，定位具体问题并反馈到Make参考，修正后再对照。不能悄悄降低还原目标；常规修正由执行者继续，不每轮要求用户审批。

### 10.2 前端I/O与性能责任

| 模块 | 输入 → 输出 | 边界 |
| --- | --- | --- |
| Make参考 | DTO演示/当前视觉 → 可运行设计与视觉参数 | 不成为App运行时数据源、身份或后台服务 |
| Page/Drawer容器 | Cost DTO、用户事件 → 加载状态、任务选择、保存后当前页更新 | 网络访问委托Cost client，不发送跨页面刷新 |
| Task editor/分配行 | 单组详情、草稿、回调 → 改金额/来源/增删行事件 | 不fetch、不修改银行事实、不接全局store；确有职责需要再拆组件 |
| Draft helper | 本组草稿/来源 → 精确分运算、即时差额、提交对象 | 无I/O，后端权威校验，不搬入Make生成的业务凑数代码 |
| 局部样式 | Make参数/现有tokens → 本模块外观 | 保留共享弹层焦点、滚动锁和关闭能力，删除被替代成本样式 |

Make流畅不代表App达标。F8在App记录抽屉打开、选来源、增删行、输入和保存刷新耗时，覆盖普通任务和100条分配行任务，区分网络等待与主线程渲染。抽屉先显示外壳/明确loading；取得来源后输入和增删不发HTTP、不重建整个页面/所有任务。出现卡顿用现有浏览器性能记录和React工具定位，再局部优化，不默认新增虚拟列表、缓存或动画依赖。

本轮只准备 Make 的设计输入，未创建 Make 项目、未上传真实业务数据、未生成替代 UI。可用 Figma Design MCP 不等于 Figma Make，不能静默用 Design 文件冒充 Make 交付。正式 Make 阶段使用 Make 的实际入口并验证其产物。

## 11. 旧代码清理与保留清单

| 删除/替换目标 | 新归属 | 不能误删的内容 |
| --- | --- | --- |
| `_cost_entries` 中 O=N 直接视为来源已确定的分支 | 单元金额判定 + 来源分配纯模块 | OA 完成态、净支出、重复 owner 完整性保护 |
| `_append_unit_allocation_entries` 只按 OA 生成一行并取组内最后日期的路径 | 稀疏分配行及来源日期；pending 单元/未定月份单独状态 | 银行 owner 日期归一化与原 OA 日期证据 |
| 已分配成本的整组 `_resolve_cost_bank_account_label` | 来源流水账户 | 银行 owner 的账户解析/缺失处理 |
| 以 `_expense_facets` 和 `expense_type` 为成本分组的 Explorer/export路径 | 主/子银行标签 | OA 原费用类型字段、OA adapter、其他页面费用分类 |
| `bank_tag_context_from_row`多字段别名/显示文案推导层级 | owner投影的显式入口映射和统一成本字段 | owner有效分类算法、合法未标记/无子级语义；原time/bank_tag和退款准入输出必须回归不变 |
| `transaction_id=''` 被当作完整已分配行的旧 DTO | 有 source 的分配行或显式 pending 行 | 原 OA 单元身份和来源详情 |
| 任务列表全量完整详情 hydration + 挂载额外 count GET | 轻量概览 + 展开详情 + 复用页头计数 | 严格 pending/stale 判定、全局任务范围 |
| Drawer 每单元一个输入的 draft/map/save 循环 | 动态来源行及对应 reducer/helper | 未保存提醒、权限禁用、竞态取消、失败保留输入 |
| `buildTaskDraft`仅allocated回填、`handleSave`无条件移出pending、保存响应硬编码allocated | 有效决定回填、纯规则重算状态、按实际状态迁移列表 | 已保存内容、其它任务脏草稿、明确stale提示和审计 |
| `_row_in_export_range`空日期字符串比较、旧成本cursor/逐OA身份假设 | 显式日期范围规则、统一排序元组、成本cursor格式版本 | 原银行流水排序/导出/cursor保持不变 |
| 被替代的`.cost-manual-allocation-*`布局/金额输入样式与Make临时运行依赖 | 与新展示对应的局部样式、现有App组件 | 共享Drawer/Table/焦点/滚动能力；旧样式仍有消费者时先迁移再删 |
| 旧 3/2/3 栏选择状态和导出 OA 费用过滤 | 4/3/5 层级 | 局部加载、显式分页、原银行流水视图 |
| 无消费方的旧 month/export 分支、旧 response别名及独占fixture | 新唯一 client/DTO | 真实仍有消费方的接口字段与共享样式 |

执行删除前：CodeGraph impact/trace 定位结构调用，rg 全仓检查符号与协议字符串（包括 tests、docs、e2e、scripts、apiMock、audit/probe）。删除后复跑同一扫描和相关测试。保留历史迁移文件用于重放；不会恢复 0162 前的旧来源矩阵、带正负 source_kind 的并行 reader。

## 12. 其他页面和文档影响

| 模块 | 本次关系 | 保护方式 |
| --- | --- | --- |
| bank-details / bank-account-balance | 只读事实/公开分类 port | 不改变分类算法、标签写入、余额/排序 API；成本分配保存前后银行事实不变 |
| workbench-relations | 读取当前关系并复用锁协议 | 不创建/撤回/修改关系或 requirement metadata；关系变化由下次 Cost GET 读取 |
| OA integration | 读取既有 canonical OA 单元 | 不更改 OA 同步、归一化、费用类型或项目事实 |
| settings / no-OA | 读取账户/标签设置，保留现有无 OA写入口 | 不加成本独立标签设置，不改变其他标签消费者 |
| permissions / operation-history | 复用 session/ACL/audit | 新详情 route登记；保存仍有审计，不引入新授权层 |
| tax/pending invoices/turnover/batch/ETC | 共同上游，但不是本次写目标 | 关键链回归证明共享 bank/OA/relation 状态未变化；不新增扇出 |
| runtime workers / read-models | 无新依赖 | 现有退役测试仍通过，无 queue/cache I/O |
| cash | 完全无输入输出 | 不读取 cash.*，不将现金金额混入成本或审计参考数据 |

实施时更新：`docs/product-specs/cost-tax.md`；Cost 模块 README/boundary/state-machine/tests/e2e-spec/implementation-notes；`docs/dev/api-contracts.md`；真实受影响的 `write-operation-impact-matrix.json` 和 `page-read-model-fact-display-matrix.json`；canonical owner matrix 登记新列语义。只更新受影响条目，不另造测试/发布门禁。

银行/关系/权限模块若公开 I/O 或锁协议没有改变，只核对并增加必要消费说明；不要机械修改所有模块文档。生产上线状态只在真实执行后记录。

## 13. 七类测试与可执行验证

| 类别 | 计划覆盖 | 位置 |
| --- | --- | --- |
| 1 业务核心 | 自动充分条件、等额歧义、增删行、双边金额、退款/非成本、零/非法/重复、旧金额待来源、来源失效、主子同名、跨月350/250、退款冲减原付款月、日期缺失 | 扩展 `test_cost_statistics_policy.py`；新增纯来源规则测试 |
| 2 Service/Repository | 同事务保存/审计、CAS、回滚、全量任务轻量化、目标详情、有界查询、旧 NULL记录 | 扩展 canonical repository/API；新增 `test_cost_statistics_source_allocation_postgres.py` |
| 3 API | 新 GET详情、PUT shape、权限、400/403/404/409、cursor全部条件绑定、3视图/导出、旧参数拒绝、保存超时后重读 | `test_cost_statistics_api.py`、frontend API test |
| 4 Read model/cache/job | 本功能不新增这三类机制；以既有退役与零 I/O断言保护。数据写后下一次 canonical GET一致性纳入服务/集成测试 | `test_read_model_runtime_removal.py` + repository/集成断言 |
| 5 前端交互 | loading/empty/error、长列表、动态行稳定焦点、来源联动、空/零、金额超额、任务草稿隔离、关闭提醒、409保留草稿、迟到响应、4/3/5层导航、权限与窄屏；App与Make同条件浏览器对照 | CostStatisticsPage/API/List 测试 + 拟独立Drawer测试；实际截图和操作记录，不新增截图baseline |
| 6 端到端 | 已有关联→等额多对多待分配→人工增行→保存→三视角/详情/导出；跨月明细及初次/下钻/导出一致；退款/非成本链；修改银行标签和撤回关系后读取新事实 | Cost e2e + 真实 PG/HTTP 集成，不仅mock |
| 7 既有回归 | 原 time/bank_tag方向金额、无OA范围、旧人工金额保留、银行余额/标签、关系/权限/导入/ETC等不被成本写入修改 | 现有对应模块测试与有限业务链 |

不建立永久冻结数据集、hash清单或额外验收平台。复用现有 pytest/unittest/Vitest/Playwright 和明确合成样例。

### 13.1 后端命令

```bash
bash scripts/verify.sh lint
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_cost_statistics_policy \
  tests.test_cost_statistics_canonical_repository \
  tests.test_cost_statistics_api \
  tests.test_postgres_migrations \
  tests.test_read_model_runtime_removal
```

新增来源规则、PG/HTTP测试文件后加入同一命令。真实 PG 测试仅使用现有 `assert_safe_test_database_url` 已确认的可丢弃测试库；不 source 指向生产的 local-postgres.env 后运行清库测试。缺测试库时如实报告未运行，不以 skip 当通过，不放宽已有测试库保护。

### 13.2 前端命令

```bash
cd web
npx vitest run src/test/CostStatisticsApi.test.ts src/test/CostStatisticsPage.test.tsx src/test/CostExplorerList.test.tsx
npm run build
npx playwright test e2e/cost-statistics-flow.spec.ts e2e/cost-statistics-relation-fanout.spec.ts --project=chromium
```

新增 Drawer测试加入 Vitest。共享组件有变才扩大共享组件回归；本次保持不改共享边界，发布前运行现有有限受影响业务链。`bash scripts/verify.sh docs` 检查文档，不能替代业务测试。

### 13.3 规划阶段验证记录

- 前一轮现状分析已运行后端上述前三个现有suite：65项通过，2.582秒；使用测试桩，不代表真实PostgreSQL事务或生产性能。
- 前一轮现状分析已运行前端上述三个现有suite：23项通过，4.45秒；有现有Node/React Router警告，没有失败。后续仅更新计划文档，未重复运行这些业务测试。
- `bash scripts/verify.sh docs`、`git diff --check` 通过；两份新增文档的本地链接已检查，无失效链接。文档检查不验证新业务逻辑。
- 完整计划汇总时另用Decimal核算5个金额样例：跨月350/250、退款1050-35、非成本100-20均逐来源闭合；400/200分配给350/250来源、600/400分配给500/500来源两例均识别为总额虽平但来源超额。仅为计划算术核对，未实现分配服务、未操作数据库。
- 再次反例审阅额外推演4组：权威单元600/400不能改为500/500；根合计700/叶子100且上游兄弟项保留；25行中7行无日期排末尾并从end-only导出排除；pending资料问题与有效来源决定可以共存。结果符合修订规则。这些只是独立计划样例推演，未验证实际App分页、持久化或浏览器行为。
- 已只读查看线上当前抽屉 UI；没有保存分配、修改筛选或写业务数据。
- 未跑新功能测试（尚无实现）、真实 PostgreSQL迁移/并发、生产性能或新版浏览器 E2E。现有测试通过只证明规划基于可运行的当前行为。

## 14. 发布顺序与任务完成条件

开发完成后，先在可丢弃本地/测试库验证追加列迁移、历史 NULL处理、业务流程和并发，再通过现有 `./scripts/deploy-oa.sh` 正式发布入口按正常授权执行。仅在正式发布/生产数据操作边界保留既有检查；日常开发不增加逐步骤审批。

任务完成要求：三个视角金额一致且正确到来源；待分配可以增删行、保存/修改/冲突重读；历史金额未丢；退款/非成本闭合；来源缺失诚实展示；API/导出同步；旧路径无生产调用；必要测试和性能测量有记录；本任务如产生临时备份已按精确范围清理。不能只以 UI 能点开或保存返回 200 认定完成。

## 15. 统一执行顺序和文件交付

以下是实际开发时的工作清单。每批完成相关普通测试和清理后继续，不逐项请求审批。Make迭代次数取决于实际问题，不预设“生成三次就算通过”；工时也不能在未实施和测量前声称准确。

| 顺序 | 依赖与任务 | 文件交付范围 | 当批必须交付的结果 |
| --- | --- | --- | --- |
| 1 | B1：把本文规则落成API/状态示例，列出正常/异常合成数据；确认现有类型和调用 | Cost模块boundary/API文档及`services/cost_statistics_*`已有类型定义；前端`features/cost-statistics/types.ts`对应定义 | 一份前后端共同使用的字段说明；source_pending、global counts、跨月日期语义一致；没有设计冻结文件 |
| 2 | B3：先实现纯来源分配规则，B2存储部分紧随其后 | 拟新增`services/cost_statistics_source_allocation.py`，对应规则测试 | 金额校验、确定性自动分配、歧义pending、退款/非成本来源与历史NULL都有正反例；尚不留可被误调用的双运行路径 |
| 3 | B2：新增列、严格读写、事务保存/审计、并发复现与局部修复 | `postgres/migrations/`下一可用migration；`services/postgres_repositories/cost_statistics_manual_allocation.py`；manual service、测试helpers、迁移/PG测试 | 新库与旧库升级可用；历史金额不丢；400/409不半写；真实PG验证保存、源变化和关系撤回 |
| 4 | B4/B5：接入统一policy、列表/详情、三视角、日期、导出与分类显式映射 | canonical repository、policy、query/manual service、`cost_statistics_bank_tags.py`、`app/routes_cost_statistics.py`、`app/server.py`最小接线 | 单一成本集合；轻量列表/定向详情；当前日期与跨期完整事实一致；新API和原银行流水视角回归 |
| 5 | B6：删除被替代运行链并测性能；同时可在步骤1后开展F1–F4设计 | 第11节列出的真实调用方、DTO、tests、scripts、局部文档；Make预览/普通设计记录 | 旧OA费用分组/整组账户与日期猜测无生产调用；SQL/HTTP耗时有实测；Make已完成浏览器迭代后才能进行UI移植 |
| 6 | F5/F6：依赖Make通过实际浏览器验证；API联调依赖步骤4可用 | `web/src/components/cost-statistics/`、`web/src/features/cost-statistics/`、`web/src/pages/CostStatisticsPage.tsx`、`web/src/app/styles.css`局部段 | 动态分配行、真实保存/冲突、4/3/5层级、详情/导出接通；旧draft、导航、冲突CSS同批删除；不修改共享组件默认行为 |
| 7 | F7/F8：移植复验、业务E2E、其他页面与性能验证 | 现有Cost组件测试/Playwright用例和真实PG/HTTP集成；必要截图和结果记录 | 同条件Make/App视觉差异已处理，代表性完整链通过，无演示数据/旧字段兜底和跨页刷新 |
| 8 | 正常发布与收尾：依赖功能、迁移、回归和测量完成 | 既有`./scripts/deploy-oa.sh`入口及相关运维记录 | 后端/前端同一发布安排，旧浏览器明确刷新；发布后只读核对；如产生本任务临时备份则按确切路径清理，禁止主库删除 |

表中backend相对路径均位于`backend/src/fin_ops_platform/`；migration实际目录是`backend/src/fin_ops_platform/postgres/migrations/`。新migration编号按实施当时仓库分配，不改0157/0162。新测试只针对本次业务风险，不为表中每个子步骤机械新增一个测试文件或审批。

后端规则和接口必须先确定。Make设计可与后端实现交错推进；App展示移植必须等Make浏览器验证完成，真实保存联调必须等新后端可用。开发过程允许小步提交，正式发布只切换到完整新链路，不上线半完成的来源分配功能。

## 16. 可直接用于开发与验收的样例

### 16.1 跨月600元的完整来源决定

以下ID全部为演示标识。设同一active关系中，OA单元U成本600.00，8月31日支出B1为350.00、建行、采购/材料款；9月2日支出B2为250.00、民生、采购/材料款；没有退款与非成本。单一成本单元且来源净额明确，系统可确定性生成两行；此例也用于人工记录编辑/回填。

下方PUT示例使用有真实人工分配资格的变体：OA原额700.00、净支出600.00，人工确认最终成本600.00，来源仍为350.00/250.00。自动600/600场景验证读取，人工700/600变体验证保存、审计和回填，不对没有任务的自动关系强行调用PUT。

```json
{
  "relation_case_id": "case-demo",
  "expected_version": 0,
  "source_fingerprint": "详情返回的现有指纹",
  "allocations": [{"unit_id": "unit-U", "amount": "600.00"}],
  "non_cost_amount": "0.00",
  "non_cost_reason": "",
  "source_allocations": {
    "cost_lines": [
      {"unit_id": "unit-U", "bank_transaction_id": "bank-B1", "amount": "350.00"},
      {"unit_id": "unit-U", "bank_transaction_id": "bank-B2", "amount": "250.00"}
    ],
    "refund_links": [],
    "non_cost_lines": []
  }
}
```

账户、标签和日期不在请求中独立填写。自动与人工两个变体各自使用真实资格，不能为了演示绕过服务端验证。

读取预期：全时间三个根视角各600.00；8月350.00；9月250.00；建行350.00、民生250.00；明细2行、原OA单元1个、来源支出2笔；详情/导出仍能追到同一个U。把B1改成400.00、B2改成200.00，即使总数仍600.00，也因B1超额而拒绝保存。

### 16.2 必须保护的失败和边界场景

| 样例 | 预期结果 |
| --- | --- |
| OA A600/B400，银行B1/B2各500 | 初始来源待分配，不给A自动塞100元B2；人工核实后提交才生成对应来源行 |
| 上例用户提交A全部600给B1、B全部400给B2 | 尽管总额1000，因B1超额100拒绝；不能自动搬100到B2 |
| 原A600/B400改成A500/B500、两笔来源各500 | 所有请求内合计虽平，仍因违反O=N时canonical单元目标而拒绝 |
| 同一OA同一来源重复两行 | 提示重复来源行，不隐式合并、丢弃或重复统计 |
| 引用别的关系/收入/已删除支出ID | 按输入错误或事实变化明确拒绝；不给任意账户选择器绕过 |
| 支出1050、明确付错退款35、成本1015 | 原支出=成本1015+退款35；若退款跨月，成本归原付款月，银行收入仍在退款月 |
| 支出100、成本80、非成本20 | 同来源的成本和非成本闭合，有非成本原因；未填来源不能当作已分配 |
| 历史unit_allocations有效、source_allocations为NULL | 原已确认金额保留；能确定则自动来源，不能则待分配，不按比例补历史 |
| 已保存来源但银行标签缺失 | 保存真实来源、金额与日期；标签显示未标记并提示维护，不能退回OA费用类型 |
| 上一场景保存后关闭再打开抽屉 | 完整回填有效金额/来源/非成本；任务仍pending，不变空表、不错误出队 |
| 有效银行记录的分类投影整条缺失 | 明确完整性错误；不将漏读伪装成“未标记” |
| 只有日期没有时分秒 | 按银行owner真实日期归月，不制造时间或误用组内最后时间 |
| 来源未定/日期完全缺失 | 全时间金额可见，年月合计不猜值；未定月份提示可解释差额 |
| 分类名称或合法层级变化 | 下一次读取当前有效标签；不复制旧标签快照作为第二事实源，现有版本失效保护保留 |
| 用户保存同时关系撤回/源金额变化/另一用户保存 | 明确冲突或按事务序得到当前有效决定；无半写、无虚假成功审计，草稿可供重核 |
| 保存网络响应丢失 | GET当前决定和version核对，不盲重试、不凭超时判断失败后重复写 |
| 搜索后命中一个任务 | row_count为命中数量，顶部counts仍是全局任务数量 |
| 上游筛选切换、迟到的请求返回 | 下游选择和cursor正确重置；旧响应不能覆盖新查询结果 |
| 选择P1→采购→材料 | P2和P1下其它合法子标签仍在对应列表；页头根合计不缩水，明细仅当前路径 |
| 无日期行与同日期来源跨页 | 每行出现一次、不丢不重；无日期排末尾，无假日期；旧成本cursor明确失效 |
| 仅截止日期导出且有无日期成本 | 无日期不混入范围，另提示未定月份金额；无时间限制原始明细仍包含这些行 |
| 支出完全由明确付错退款抵消、N=0 | 不产生成本行，不新增无成本可分的任务，原银行收支正常 |
| 连续两次修改同组来源 | 当前表保存当前决定，既有审计按version保留各次完整来源，无新增历史表 |
| 单笔流水拆成多个成本行 | 成本按分配金额相加，流水笔数按ID去重，不把行数等同笔数 |
| 超过现有导出行数上限 | 明确提示缩小范围，不截断后仍称导出成功 |

样例与普通测试使用同一业务含义，但不新增永久冻结数据文件或hash校验。合成样例放现有测试位置；真实财务数据不进入测试仓库或Make演示。

## 17. 计划复审

| 用户要求 | 审阅结果 | 计划中的落实 |
| --- | --- | --- |
| 模块化、清晰 I/O | 通过 | Cost owner读写，银行只读port，纯规则无I/O，route只HTTP |
| 简单、避免过度设计、完整闭环 | 通过 | 复用一表一列、现有服务；退款/非成本只加必要稀疏来源明细；无新平台 |
| 高性能 | 方案通过，效果待测 | 去掉重复全量count/详情，稀疏计算和批量分类；第8/10.2节分别测后端和App交互 |
| 旧代码必须清理 | 通过 | 第11节明确删除符号、消费方、测试及保留理由 |
| 不污染其他页面 | 方案通过，需回归证据 | 写入仅成本决定+审计，不改共享业务事实或广播刷新 |
| 指出不合理理念 | 通过 | 第1.3节纠正独立选标签账户、凑数、绝对零bug、全串行、误删安全措施 |
| 备份清理、禁止删主库 | 通过 | 默认不备份；如流程要求，仅清理本任务副本；禁止主库删除/覆盖恢复 |
| 禁止兜底代码 | 通过 | 明确NULL/pending/invalid分支；禁止旧金额/标签/账户推测、双读及隐藏兼容 |
| 不默认加hash/冻结/baseline/gate | 通过 | 只保留现有指纹/CAS/迁移测试，未设计新hash或性能门禁 |
| 前后端分开、后端优先、Make做UI | 通过 | B1–B6 / F1–F8，先Make浏览器验证与迭代，再移植App，移植后复验 |
| App尽量还原Make | 方案通过，效果待验证 | 第10.1节明确同条件比对、视觉参数、局部样式和差异处理，不靠复制整套工程或主观百分比 |
| 不使用GSD、先计划不实现 | 通过 | 本轮只写计划/设计交接，不改业务代码或数据库 |

复审修正已并入正文：避免「总额闭合但来源超额」；补退款/非成本来源；保留 0162 后旧金额但不反推来源；避免页头count造成全量额外查询；防止成本未知来源从总额消失；保留三段原始标签路径；明确Make只做设计和源代码不是事实依据；按用户最新确认改为来源付款月份，补齐未定月份展示、跨月退款及跨期读取完整性；指出现有 KEY SHARE 不是金额更新保护，明确 B2 的真实并发验证与局部修复责任。

第3.7节跨月日期已按用户回复落定。新增字段和实现细节给出可执行方案，不要求每个内部选择再设审批。真实 PG 并发与性能仍须在实施时验证；没有实施前，不把本表的「方案通过」写成「功能验收通过」。

本次前端流程再次复审：已补Make实际浏览器验证、定点修改循环、移植版本记录、App同条件还原复验、局部样式隔离和交互测量；没有增加逐轮审批、GSD、冻结设计或视觉门禁。前端完成还要求Make关键问题已处理、App无未解释的明显视觉/行为偏差。当前仅计划，没有Make验证或App还原结果可报告。

完整计划最终复审又修正三项具体遗漏：统一`allocation_state=source_pending`，保留任务counts的现有全局口径，清理成本标签多字段猜测并区分合法未标记与投影漏行。第15节已明确依赖/文件/交付，第16节提供可执行金额与失败样例。设计可进入实施；真实PG锁顺序、目标规模性能、Make可运行预览和App视觉还原必须在相应步骤实际验证，不以本计划的结论冒充结果。

### 17.1 再次反例审阅结果

| 问题 | 具体失败场景/证据 | 修正和实施责任 |
| --- | --- | --- |
| 单元权威目标校验不够具体 | 600/400改成500/500，来源和请求总额仍平 | B2/B3逐单元核对canonical目标；O≠N保持原规则 |
| 保存但pending丢回填/错误出队 | 旧Drawer仅allocated回填，save无条件移出pending，service硬编码allocated | B4/F6按有效决定回填、重算状态并保留仍pending任务 |
| 多层分面过滤可能收窄上游 | 从叶子结果生成各栏会丢兄弟选项 | B5/F6每栏只用上游条件，保持根summary口径 |
| 空日期导出/分页遗漏 | 空字符串可能通过仅end_date范围 | B5明确未知日期、统一排序元组和成本cursor普通格式版本 |
| 来源历史审计不足 | 现有事件只保存单元总额 | B2向既有同事务审计加入完整来源决定及version |
| N=0被过度扩展 | 无成本可分却要求填退款矩阵 | B3维持无成本，不增加此任务 |
| PUT样例和压测边界不清 | 自动关系未必有PUT资格，压力矩阵不能默认为生产操作 | 第16.1分开自动/人工变体，第8.2明确隔离压测 |

以上均落在现有模块和普通测试内，没有新增平台、worker、审批或冻结合同。cursor格式版本用于拒绝旧成本分页语义，属于普通版本控制，不是新hash/gate。修订后计划可实施；真实PG锁顺序、性能和UI效果仍必须在相应步骤验证，文字复审不能替代这些证据。未发现必须扩大为全站重构的依据。
