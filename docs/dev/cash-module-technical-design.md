# 现金模块技术设计：后端、数据库、API 与一致性

更新日期：2026-09-07。工作分支：`codex/cash-ledger`。

状态：**R1–R7已接受；本轮用户明确授权后端实施、测试、提交/推送及部署。后端实施中，真实测试与发布结果只以实施计划执行记录为准。** 本文继续拥有字段/API/事务规格，不把规格等同于已通过验收。

本次共四份配套文档：业务需求和 Excel 解释以[现金模块开发设计](../product-specs/cash-module-design.md)为准；页面、表单和 Make 改稿见[UI 设计](../product-specs/cash-module-ui-spec.md)；执行顺序、旧链清理和总体测试安排见[实施计划](cash-module-implementation-plan.md)。本文拥有技术字段、数据关系、服务 I/O、请求语义和事务细节。将来修改需求时，四份文档的受影响部分须同步修改，不保留相互冲突的旧规则。

本文使用三种标识：

- **已确认**：用户已经明确的业务要求，例如独立现金流水、手工录入、任务来源、全账删除、不写全局历史。
- **技术方案**：据当前需求提出、可据此细化测试的实现方法；随完整设计一并审阅，不代表已经运行。
- **待技术核实/使用配置**：OA原始字段由开发者查证，真实账户/期初/任务值由用户使用时配置；不把已接受R1–R7重新列为待确认。新发现会改变业务范围的冲突必须明确说明，不猜测。

这里的“直接可执行”是明确工作落点、输入输出和验收例子，不是把缺少事实依据的账务口径写成代码。完整设计批准前不实现应用代码，不生成 migration，不运行真实数据修改。本文不使用 GSD，不新增逐步骤审批机制。

## 1. 最小模块结构与文件职责

### 1.1 单向调用边界

```text
现金页面局部组件 → cash API client → cash route → cash service → cash repository → 同库 cash.*
                                           │
                                           └→ OA owner 的项目资料只读方法（仅项目选择/配置）

现有 session / 页面 ACL → route 授权
现金业务事实 ─X→ 普通财务表、全局操作历史、全局任务、全局搜索/统计
普通页面事实 ─X→ cash service / cash repository
```

只有一套现金事实。往来账总表、现金流水、有票支付、刘树刚账及子表都是这套事实的查询结果，不各自写入一份流水。

### 1.2 拟议文件落点

以下现金文件名均为候选，不表示当前存在；现有文件仅在集成确实需要时改动。

| 责任 | 文件/目录 | 输入与输出 | 不承担 |
| --- | --- | --- | --- |
| 页面组合 | `web/src/pages/CashPage.tsx` | 当前 Tab、可信页面可用性 → 当前现金视图 | 全局 store、第二套 Router、跨页现金 badge |
| 前端请求与 DTO | `web/src/features/cash/api.ts` 及同目录类型 | 表单/查询参数 → 本文现金 API；响应 → 局部组件 | 普通银行/发票/往来 API、模拟成功、浏览器全量计算 |
| HTTP 边界 | `backend/src/fin_ops_platform/app/routes_cash.py` | 已认证身份、请求 → 严格参数/命令；结果 → HTTP | SQL、账务规则、读取 cookie 的业务 service |
| 业务方法 | `backend/src/fin_ops_platform/services/cash_service.py` | 明确命令/查询参数与 actor → 业务结果 | 整个 Application、HTTP response、普通账 repository |
| 现金持久化 | `backend/src/fin_ops_platform/services/postgres_repositories/cash.py` | 现金查询条件、调用方事务 → cash.* 事实 | OA 网络 I/O、用户权限判断、全局 audit/job 写入 |
| OA 项目只读 | 现有 OA integration owner 内的窄方法 | 项目 ID/分页条件 → 精确项目资料与阶段字典 | OA 财务单据、写回、普通 App completed override |
| 最小组装 | 现有 `application_factory.py` / `server.py` | 明确 cash repository、项目只读依赖、时间来源 → cash service | 启动时拉项目、初始化业务数据、跑任务 |

初始保持一个现金 service 和一个现金 repository。只有实际体量妨碍维护时，才在同一 owner 内拆出任务/结算文件；不提前引入 facade、manager、factory、策略注册平台或一张表一个 service。复用当前工程的事务/连接池和纯组件，不复制旧模块的内存 fallback 或完整状态快照。

### 1.3 最少 service 方法

这些是职责名称，不是冻结接口；实现时保持一个方法一个明确业务动作。

| 方法职责 | 输入 | 输出 | 事务 |
| --- | --- | --- | --- |
| `list_flows` / `get_flow` | 现金筛选或 ID | 有效流水、关联概览、余额/分页 | 短只读快照 |
| `create_flow` | 稳定提交 ID、现金收付字段、actor | 新流水或同次提交的已有结果 | OA 校验后一个现金写事务 |
| `update_flow` | ID、预期版本、获准修改字段、actor | 新版本流水及同步关联结果 | 一个现金写事务 |
| `delete_flow` | ID、预期版本、actor | 删除结果、受影响任务/事项版本 | 一个现金写事务，无 OA |
| `confirm_task` | 模板/月、预期版本、新流水或已有流水引用 | 月度处理结果与唯一现金引用 | 复用同一个现金写事务 |
| `mark_task_unpaid` | 模板/月、预期版本 | 尚未收付处理结果 | 不产生现金 |
| `complete_check_task` | 核对任务/月、预期版本、必要备注 | 核对已完成 | 不产生现金或结算 |
| `reopen_check_task` | 核对任务/月、预期版本 | 撤销误点后的待核对状态 | 不产生现金；已确认纠错入口 |
| `record_settlement` / `correct_settlement` | 事项、类型、金额、日期、可选既有 flow | 结算及事项新版本 | 一个现金写事务，不另开内部事务 |
| `create_item` / `correct_item` | 已确认的事项字段、预期版本 | 事项和版本 | 不自动生成虚构现金 |
| 三类 `query_report` | 各报表自身筛选 | rows、summary、明细 | cash.* 短只读快照 |
| 配置方法 | 账户/分类/模板/允许阶段集合、预期版本 | 配置新版本 | 本模块配置事务 |

归还/任务调用的内部写方法接收调用方已经持有的事务对象，不重新开始/提交事务，不在 service 间用 HTTP 调自己。

## 2. 数据类型、身份与公共约束

### 2.0 先分清“银行流水、现金流水、录入流水”

| 名称 | 事实源与字段归属 | 本功能怎样处理 |
| --- | --- | --- |
| 现有 App 银行流水 | 现有 `app.bank_transactions` 及其 owner；领域 `BankTransaction` 包含账户、方向、金额/有符号金额、银行序号、导入批次、银行余额、核销金额、来源键等 | 不改表、不继承 DTO、不复制进入 cash；普通手工银行录入仍是普通银行池的入口，不是现金录入入口 |
| 本模块现金流水 | `cash.flows`；字段见 §3.5 与 §3.11，银行账户如属于现金管理范围也用本模块账户 ID | 一份现金事实，手工与任务共用，不因资金存在银行就转用普通银行模型 |
| 手工录入的流水 | 手工创建命令，成功后就是 `source_kind=manual` 的 cash flow | 未提交表单只在当前页面内存；不建 `cash.manual_flows`、录入中间池或草稿同步表 |
| 任务生成的流水 | 同一 cash flow，来源为 `monthly_task`，关联月实例 | 不建另一张任务流水表；关联已有手工流水不改来源、不复制 |
| 报表中的一行 | flow、item 或 settlement 的查询 DTO | 行粒度由该报表定义；不是每行再持久化成一条银行流水 |

现有普通 `BankTransaction` 的 `data_fingerprint/source_unique_key/source_batch_id/written_off_amount` 服务于原银行导入/核销，不是现金表“字段齐全”就应照搬的字段。已有 hash/安全措施不删除，新现金功能也不新增这些无需求字段。以上源码核对仅用于区分模型，不授权现金读普通事实。

### 2.1 数据类型

| 类型 | 技术方案 | 适用规则/限制 |
| --- | --- | --- |
| 内部 ID | 随机 UUID；创建类请求在一次提交期间使用同一个 ID | 不是 hash；重试不能换 ID；用户明确重新录入才产生新 ID |
| 金额 | Python Decimal、PostgreSQL numeric、API 十进制字符串；字段级候选尺寸见下文 | 人民币两位，单笔最大9999999999999999.99，不建多币种平台 |
| 业务日期 | 日期类型；API `YYYY-MM-DD` | 补录不得早于账户起算；实际收付不得晚于上海今天，计划日期独立 |
| 月份 | 数据库统一存当月第一天，API `YYYY-MM` | 账单归属月不等于实际收付月 |
| 系统时间 | 带时区时间，服务端生成；展示 Asia/Shanghai | 不信任客户端创建时间 |
| 版本 | 正整数，初始 1，每次实质变更递增 | `expected_version` 比较失败即冲突，不覆盖别人修改 |
| actor | 从现有可信 session 获取账户/名称等必要快照 | 客户端不能指定；详情显示，列表按UI列配置；不从audit反查 |
| OA 项目身份 | OA 稳定 ID + 必要名称快照 | 原始 ID 类型/字段要先核实；不按名称匹配、不使用普通项目 override |
| 文本 | 有长度上限的普通文本；空字符串/空值规则统一 | 必填与上限见§3；不允许任意JSON代替核心字段 |

核心金额不能用浏览器 `Number` 累计后写回；展示复用现有金额格式，不能把格式化后的逗号字符串当持久化金额。

#### 字段尺寸与空值：实施技术规格

以下类型是按已接受规则收口的技术规格，不是冻结contract；普通版本、类型与测试足以管理演进。数据库可NULL不等于该业务允许省略，条件必填见§3。

| 简称 | PostgreSQL / API | 约束与来源 |
| --- | --- | --- |
| ID | `uuid` / UUID 字符串 | PK 非空、无运行时补造默认；新建ID由一次提交产生，重试沿用；服务端生成月实例ID例外 |
| Money | `numeric(18,2)` / 不含分组符的十进制字符串 | 16位整数+2位小数；单笔上限9999999999999999.99；不接受超精度后隐式舍入 |
| Label | `text` / string；建议字符长度1–120 | 用于本地名称/标题/人员，去首尾空白后非空；不截断保存 |
| Content | `text` / string；建议1–1000 | 费用内容/事项说明；是否必填见相应业务类型 |
| Note | `text` / string或null；建议最多2000 | 非必填说明，空白统一为null；无默认“其他” |
| SourceId / SourceLabel | `text` / string或null | OA ID/code/name不得按Label的120上限截断；原始长度/类型在B01核实，未核实不伪造上限或编码 |
| Version | `integer` / integer | `NOT NULL DEFAULT 1`、正数；客户端仅提供expected版本，绝不写新版本；超过容量明确报错，不回绕 |
| SystemTime | `timestamptz` / 带时区ISO字符串 | 非空；创建时由DB时间初始化，实质修改时repository写updated_at；普通读取不改时间 |
| Month | `date` / `YYYY-MM` | 非空时必须为月初；接口规范化为当月1日，不接受任意日冒充月 |

金额输入顺序：限定字符串长度和十进制语法 → Decimal解析 → `is_finite` → 小数位/金额范围 → 收付/期初符号规则 → 写库。拒绝 NaN、Infinity、科学计数、千分位、JSON数字/布尔值和超精度值；不能让 `numeric(18,2)` 先悄悄四舍五入再当合法输入。DB另有NOT NULL、有限值/范围和正数约束；期初允许正/零/负且负数警示；普通原额/分配必须正数，不能按同一类型混用符号规则。

单笔存储上限不等于聚合金额上限：SUM/余额可能超过16位整数，查询结果保持PostgreSQL精确numeric并序列化十进制字符串，不能再次强转numeric(18,2)、截断或当非法单笔金额丢弃。响应校验区分单笔字段与派生汇总的范围；汇总不回写单笔字段，展示保持字符串/BigInt。服务层需要做金额运算时明确Decimal精度或用已批准两位金额的精确最小单位运算，不依赖默认上下文对大额累计悄悄舍入；不新增金额库。

PostgreSQL 的声明精度可能触发舍入，NaN也不能只靠“金额>0”排除，参见[数值类型说明](https://www.postgresql.org/docs/16/datatype-numeric.html)。这里的API前置金额校验是输入正确性，不是新增审批门禁。类型尺寸建议必须用边界测试验证，不能宣称单一CHECK能恢复已经舍入的原输入。

现有 `web/src/features/money.ts` 已按字符串和BigInt格式化，不需要再写金额库；但它会把空值默认显示0.00，也会对第三位小数舍入。现金client须先验证Money DTO，null显“—”，非法响应显示错误；只给formatter传已验证金额字符串。不得把业务错误交给展示函数兜底，也不修改普通页面既有formatter行为。

写请求统一：未知字段400；新增必需字段缺失400；部分更新中“未出现”=保持原值，明确null只可清空可空字段，空对象不作为成功修改。非空字段传null/空白拒绝，不能把0、false或null用 `or default` 混为缺失。候选路径沿用PUT作为字段白名单部分更新，文档显式约定此语义，不再同时新增PATCH别名。

数组必须有界；建议单次分配最多100条、查询页默认50最大200、关键词最多200字符。分配上限是事务资源建议，正式业务样例若超出先调整并测量，不拆成前端多次提交破坏原子性。布尔值只收JSON boolean，日期不能由浏览器本地时区隐式变日；筛选SQL值全部参数化，排序只映射白名单，关键词中的SQL通配符按普通文字转义。

### 2.2 身份与重试范围

- `flow.id` 同时作为这笔现金创建的稳定提交身份；重复点击/响应丢失不再造一笔 flow。
- 已存在且未修改的同次创建：比较规范化后的白名单业务字段，相同返回已有结果；不同返回 409。比较字段，不计算内容 hash，不保存第二份请求正文。
- 已经编辑、删除或进入不允许重放状态：明确冲突，不通过 upsert 恢复旧内容。
- `template_id + month` 只解决“月份处理记录唯一”；不能替代每笔实际收付的 ID，也不能证明某笔已有手工流水就是某项任务的付款。
- 关联既有流水由用户明确选中 ID，不能凭同日、同金额、同人员自动合并。
- 删除后旧创建重试的身份存续方案见第 4 节。只保留当前行主键而删除整行，不能覆盖这个失败场景。

复合创建的“同内容”包括flow全部可写业务字段、命令入口来源、目标模板/月、按item ID排序的`related_items`集合及其业务字段、按item ID排序的origin_items绑定集合，以及按分配ID排序后的`allocations`集合（来源/目标ID、kind、amount、date、remark）。不比较数组顺序、actor、创建时间、由OA生成的名称或旧expected版本这些非业务意图字段；新建时取得的可信身份仍不可被覆盖。子对象缺失、多出、归属改变或已更正均不能只因flow金额相同返回成功。

重放只读取仍有效的原对象关系，不重建子对象。新建事务最终让新对象version=1；初次复合新建中的初始分配不把刚建flow先升到2；origin_items中的既有item本次递增一次，不是新对象version1。之后增/改/撤现金分配或任务关联必须递增flow.version；复合请求自己的新建事项/分配版本也参与未修改判断。已存在的目标借款后来有其他还款，不等于本次现金被修改，不能将其旧expected_item_version再次当作重放写授权；返回当前有效结果，不重做最初副作用。用同一短快照一致读取这些关系，不能拼接不同快照证明成功。无法证明是同次未变结果则409，不补请求正文副本或hash库。

R7的project_mode是创建时的上下文校验方式，不是第三种流水来源或持久化状态。规范化业务结果包含最终项目ID和真实分配目标；existing_item的锚点须在原有效分配中，不能用不参与结算的事项借用项目。证明是原未变结果后返回当前结果，不重新请求OA或用原锚点旧版本重做结算；新动作才执行当前资格/CAS。两种上下文不建立请求副本或hash。

## 3. 数据库字段与关系：唯一实施模型

### 3.1 表数与关系

八个核心业务实体为 accounts、categories、settings、flows、task_templates、task_occurrences、items、settlements，均在同库 cash schema。另有两张很小的必要表：

- cash.bill_labels：稳定的“银行+账单别名”身份。同银行两张卡不能按银行名合并；改别名或删除某月账单也不应改变跨月行身份。只保存标识/名称/启停，不管理卡号、额度、银行卡接口或账单导入。
- cash.deleted_submission_ids：已删除 flow/item 的最少创建身份，见§4；不保存金额/人员/正文，不是流水或历史表。

共10张表，不是10个模块。月/年/总表/有票/个人账均为查询，不建报表副本、不建OA项目表、费用流水表或任务流水表。字段尺寸一律引用§2.1；以下 NN 非空、O 可空、C 按类型条件非空。没有列出的默认业务值不得自动补入。

```text
accounts ← flows → categories
             → task_occurrences → task_templates
             ← settlements → items → bill_labels
items.origin_flow_id → flows；company_receivable.ticket_source_id → items(ticket_source)
settlements.source_item_id → items(ticket_source/expense)
settings：单行OA阶段允许集合；deleted_submission_ids：只有已删类型+ID
```

### 3.2 账户 cash.accounts

| 字段 | 类型/空值/默认 | 写入与更正规则 |
| --- | --- | --- |
| id | ID NN，无默认 | 稳定身份，不可改 |
| name | Label NN | 用户明确命名；不按名称合并 |
| kind | cash/savings，NN | 实物现金或纳入现金管理的储蓄账户；无credit_card |
| opening_date | date NN | 该日开账前的已知起算日；当日流水参与余额 |
| opening_amount | Money NN | 用户明确期初，可正/零/负；负数提示核对，不自动补平 |
| enabled | boolean NN，true | 新收付只选启用账户；停用历史仍显示并算余额 |
| remark | Note O，null | 用途说明 |
| version,created_at,updated_at | Version/SystemTime NN | 常规配置CAS/时间；不是逐笔余额版本 |

允许更正起算日/金额，返回受影响期间提示；新起算日不能晚于该账户最早有效flow。更早补录先更正起算与期初；日期更正不能把旧流水偷偷排除。无期初不能保存账户为假0；引用后仅停用、不删除。kind仅无引用时可更正，有引用改含义须新账户，不将信用卡变现金资产。

### 3.3 分类 cash.categories 与账单别名 cash.bill_labels

| 表/字段 | 类型/空值/默认 | 含义 |
| --- | --- | --- |
| categories.id/name | ID/Label NN | 明确本地分类身份/名称 |
| categories.group | receipt/payment/turnover NN | receipt用于收款，payment用于付款，turnover可用于收款/付款；transfer类别可不选 |
| categories.enabled/remark | boolean NN true / Note O null | 有引用仅停用；名称只做不改变含义的更名 |
| bill_labels.id | ID NN | 跨月稳定身份；不是账户ID或卡号 |
| bill_labels.bank_name/label | Label NN | 银行及可辨的账单别名；同银行不同卡用不同ID |
| bill_labels.enabled | boolean NN true | 停用不隐藏旧矩阵行；有引用不删除 |
| 两表version/created_at/updated_at | Version/SystemTime NN | CAS与系统时间 |

分类group有引用后不可换业务含义；另建新类。颜色来自往来处理方向，不从categories.name或人员名字推断。账单别名在个人账录入旁提供轻量管理入口，不新增一级Tab、卡片权限或独立产品。

### 3.4 设置 cash.settings

字段为id(smallint PK且CHECK=1)、allowed_project_stage_codes(text[] NN、无null元素)、project_selection_configured(boolean NN false)、personal_opening_date(date O null)、version(Version NN)、updated_at(SystemTime NN)。个人账起算与账户现金起算独立，不从最早借款日期猜完整历史。

migration只建立固定行 id=1、允许集合[]、version=1，不预选业务阶段。GET缺行明确配置故障，不补建、不假空。允许集合按权威字典校验、去重排序，结束code不能保存。第一次显式阶段PUT即使仍[]也将project_selection_configured设true并递增version；此后同集合no-op。GET configured直接读此布尔值，不能再用version>1推定，避免个人起算修改误使阶段已配置。无项目业务允许提交，空允许集合不影响它。

settings/personal-opening独立命令设置/更正个人起算日期：先声明记账起点，再手工登记该日起算未结，无旧欠款时无需伪造金额0的item。不得把‘已录齐期初’设为保存日期的前置条件或将未录完冒充用户确认零。coverage表示声明的记账范围、不是实务已全部核对的证明；页面金额仅汇总已录事实。未设置时个人账coverage=unconfigured，不装已知零。个人loan创建/更正先共享锁settings起算，须已设起算；起算更正按settings→items锁序执行。opening日期等于该日，普通个人本金不早于该日。改起算不能晚于既有普通个人本金/结算，同事务同步opening事项日期但不自动改金额；个人起算与现金账户余额无关。不新增余额快照或配置平台。

### 3.5 现金流水 cash.flows

| 字段 | 类型/空值/默认 | 规则 |
| --- | --- | --- |
| id | ID NN | 稳定创建ID，同意图重试不变 |
| occurred_on | date NN | 实际收付日，不晚于上海当前日，不早于涉及账户起算日 |
| kind | receipt/payment/transfer NN | 无默认，互转同一条flow |
| amount | Money NN | 严格正数；退款另记真实收款，不用负付款 |
| from_account_id/to_account_id | UUID FK C，null | receipt仅to、payment仅from、transfer两端不同且均有 |
| category_id | UUID FK C，null | receipt/payment必填且类别适用；transfer必须null（不将其伪装收入/费用） |
| oa_project_id/project_name_snapshot | SourceId/SourceLabel O，null | 同空/同有；一flow一个项目，可无；selection由OA只读确认，existing_item由服务端继承本地事项快照 |
| person_name | Label O，null | 业务报销/经办对象，不等于录入账号，不按人名自动归类 |
| content/remark | Content NN / Note O null | 用途必填、补充可空，无“其他”默认 |
| source_kind | manual/monthly_task NN | 由入口设定，任何编辑/认领不得改 |
| task_occurrence_id | UUID FK O，null | 一flow至多一月任务；monthly_task创建必须有，manual可后认领 |
| created_by_account/created_by_name | text NN / SourceLabel O | 可信session账号与可用名称；不从请求/audit反查 |
| version,created_at,updated_at | Version/SystemTime NN | 服务端生成；日期/金额/分配/任务关系实质改动按§5.7传播 |

不存逐笔余额、报表合计、现金状态副本、银行卡流水序号、导入批次、hash或deleted_at。收付可改日期/金额/账户/类别/项目/人员/内容/备注；方向变更必须同时满足全部关联规则，不静默解绑。transfer禁止建债务/费用事项、分配或认领收付任务。不可编辑ID、来源、actor和创建时间。错误任务认领允许显式解除manual flow关联；monthly_task来源flow不能丢失其创建月份，改错归属走删除错误记录/明确重录真实业务，不伪装来源。

### 3.6 模板 cash.task_templates

| 字段 | 类型/空值/默认 | 规则 |
| --- | --- | --- |
| id/title/kind | ID/Label/receipt-payment-check NN | 模板身份、内容、处理类型 |
| execution_day/remind_days | smallint NN / smallint NN | 分别1–31、0–31；明确资源范围，不自动钳值 |
| effective_from_month/effective_to_month | Month NN / Month O | 起止有序，含端点；新建/重新启用只能当月或未来 |
| enabled | boolean NN true | 关闭未来待办，不删历史记录 |
| default_account_id/default_category_id | UUID FK O | 用户明确的预填；实际确认仍验证 |
| default_amount | Money O | 明确月目标建议，不是默认单笔支付；check必须null |
| instructions | Note O | 办理参考 |
| version,created_at,updated_at | Version/SystemTime NN | 模板配置CAS，不覆盖旧月快照 |

check的金额/账户/分类均null。类别有历史后不得换为别的kind，另建模板；标题/日期/默认额/说明可面向未来修改。当月调整走occurrence。停用/重启/未来生效及旧月物化算法见§7.3，禁止只改enabled而丢历史。具体12项日期/金额由用户使用时配置，不在migration复制Excel的冲突日期或真实卡资料。

### 3.7 月度处理 cash.task_occurrences

| 字段 | 类型/空值/默认 | 规则 |
| --- | --- | --- |
| id/template_id/month | ID/UUID FK/Month NN | 月唯一(template_id,month)；服务端生成id |
| due_on | date NN | 当月计划日，可显式改到邻近月份，不改归属月；调整范围归属月前后各31天 |
| planned_amount | Money C，null | 收付月目标，未填写允许null但不能现金确认；check必须null |
| processing_state | pending/unpaid/checked NN | 仅记录用户处理意图：收付pending/unpaid，check pending/checked；不是已付金额状态 |
| template_values_snapshot | 固定jsonb NN | 精确键见下，无任意JSON透传 |
| note | Note O | 本月说明 |
| version,created_at,updated_at | Version/SystemTime NN | 当月配置/现金关联变更一次递增 |

快照精确键：template_version、title、kind、remind_days、instructions、default_account_id、default_category_id。所有键均出现，可空字段显式null。due_on/planned_amount独立拥有当月计划，不把default_amount重复存成另一可编辑金额。生成月实例时planned_amount由当时用户显式模板默认预填（否则null），due_on按短月规则生成。实际金额、state、is_over_plan、is_overdue均查询推导，不保存独立paid累计。

未落库待办occurrence_id/version=null；row_key=template_id+month普通拼接；首次动作提交expected_template_version和expected_version=null。GET只读。历史/暂停月不由当前模板重造，详见§7。

### 3.8 事项 cash.items

只允许四种类型：loan（已实际发生的借款/代付义务）、company_receivable（明确公司报销/垫款应收）、expense（真实费用事实）、ticket_source（票据来源）。账单是义务/费用的明确归属字段，不再另建重复“账单本金”。

| 字段 | 类型/空值/默认 | 规则 |
| --- | --- | --- |
| id/type | ID/上述enum NN | 类型创建后不可改；需要改事实类型时明确纠错 |
| origin_date/original_amount | date/Money NN | 实际日期不晚于上海今天、原额为正；opening是该日起算未结额，不冒充历史总本金或未来计划 |
| is_opening | boolean NN false | 仅loan/company_receivable可true；无origin_flow，不进入本期新增本金或现金收入 |
| obligation_direction | receivable/payable C | loan必填；company_receivable固定receivable；expense/ticket_source为null |
| ledger_group | company/external_person/personal C | loan必填；company_receivable固定company；expense/ticket_source为null |
| counterparty | Label C | 两种义务必填；personal为明确刘树刚账归属，不靠名字匹配；其余null |
| oa_project_id/project_name_snapshot | SourceId/SourceLabel O | 成对快照；可无；拥有来源flow时必须和flow项目相同 |
| origin_flow_id | UUID FK O | flow建立的loan/expense或迟录现金补绑定的既有loan；原额为明确份额；其他类型null |
| origin_mode | created/linked O | 与origin_flow_id同有/同空；created表示该flow新建事项；linked表示既有真实loan补绑定，或显式来源纠错中loan/expense改绑至正确现金。普通origin_items仍仅loan；由服务端设，不据时间戳猜所有权 |
| bill_label_id/bill_month | UUID FK / Month O | 两者同空同有；loan/expense可有，其他null；跨月稳定身份用bill_labels |
| ticket_provider/ticket_provided_on/ticket_description | Label/date/Content C | 仅ticket_source必填，其origin_date=provided_on；其余null |
| related_obligation_id | UUID FK O | 仅expense可指明确loan/company_receivable，用于往来费用展示，不自动结债、不占现金；无归属费用留在费用详情而不混总表 |
| ticket_source_id | UUID FK O | 仅company_receivable可关联本模块已有ticket_source，表示明确应收来源；不占票额、不自动造应收 |
| content/remark | Content NN / Note O | 明确内容/说明；不用备注保存结构金额 |
| version,created_at,updated_at | Version/SystemTime NN | 本体、来源可用额/目标未结额变化递增 |

字段适用规则同时在类型校验与DB CHECK表达。非适用字段必须null，is_opening非义务必须false。personal loan只用receivable；company/external可应收或应付。origin_flow建立loan：receivable对应payment，payable对应receipt；建立expense对应payment，origin_date=flow.occurred_on。独立items可登记已实际发生但现金尚未补录的业务，没有flow时不创造现金。尚未实际代付的个人账单只作为月任务计划目标，不提前造真实个人借款；费用若已真实发生可先登记expense，后付款关联。opening旧未结在起算日只入期初调整，不重复计新增。

期初历史项目识别是R3初始化的具体化：首次现金池为空时，is_opening=true的loan/company_receivable可以通过OA all识别真实存在的历史项目，包括已结束项目，不按现金自由新增的允许阶段过滤。仍由OA owner只读验证ID/名称，不采信客户端快照；只建立无origin_flow的旧未结事项，不生成现金、不开放普通新增项目候选。后续真实结算才能按R7继承此本地事项。OA项目已消失且本地没有可信快照时，明确资料缺失，不造ID、不按名称猜、不悄悄改无项目。此窄规则只适用期初义务登记/项目识别，不让普通非期初事项或新本金借道；不新增表或第三种FlowCreate模式。

真实花销唯一来自expense原额减expense_refund。已独立登记费用后，现金付款只建立expense_payment分配，不重复建expense。原借款/还款/公司回款不自动建费用。一个flow复合建多个items用related_items[]；额度分为§3.9两个固定观察维度：债务资金归属与费用支付/退款。各维度不超现金原额，不能横向相加成两倍现金。同一费用不能既以来源flow新建又expense_payment重复标付；一笔代付可建立loan，同时用expense_payment明确支付已登记expense，不再新建费用或现金。费用与义务展示归属用related_obligation_id明确，不从同银行同月猜测。

票据来源提供金额、可用额度与义务余额、费用净额分别计算，不共用万能remaining_amount。独立company_receivable可明确关联ticket_source以展示实际回款，但不能由“交了票”自动推导其应收金额。

### 3.9 分配 cash.settlements

公共列：id(ID PK)、kind(下表enum)、amount(Money正数)、occurred_on(date)、item_id(UUID FK可空)、flow_id(UUID FK可空)、source_item_id(UUID FK可空)、remark(Note可空)、version/created_at/updated_at。不新增任意metadata。

| kind | 目标item_id | 现金flow_id | 来源source_item_id | 金额作用/上限 |
| --- | --- | --- | --- | --- |
| cash_repayment | loan必有 | 必有，方向与义务一致 | null | 减债务；应收用receipt、应付用payment；不确认费用 |
| company_collection | company_receivable必有 | receipt必有 | null | 减公司应收；对应“报账提现”，不再次減个人债务或费用 |
| expense_payment | expense必有 | payment必有 | null | 记录已支付，不再确认费用；不超过原费用未付额 |
| expense_refund | expense必有 | receipt必有 | null | 真实费用退款一次减净费用；不超过原费用可退额，不把普通报销当退款 |
| ticket_use | 必须null | null | ticket_source必有 | 用途remark必填；只占票据额度、不减债务 |
| ticket_offset | loan或company_receivable必有 | null | ticket_source必有 | 同一次使用同时占来源及减债务，不额外生成ticket_use |
| non_ticket_offset | loan或company_receivable必有 | null | 可为expense或null | 无票费用冲抵有expense；其他明确非现金调整须remark说明，不能造费用 |

现金分配日期必须等于flow.occurred_on；改flow日期同事务同步相关现金分配日期，不移动独立非现金事实。非现金日期不能早于来源/目标起算发生日或晚于上海今天；现金结算不能早于目标已知起算日。所有参与项目必须与同笔flow一致；非现金来源和目标有不同项目时拒绝，null视为明确无项目而非通配。票据只使用无目标时沿用来源项目。

每个flow有两个固定口径，不建通用维度引擎：①义务资金占额=origin_flow所建loan本金+cash_repayment+company_collection；②费用占额=origin_flow所建expense原额+expense_payment（payment）或expense_refund（receipt）。每个口径各自≤amount，允许余量；二者不得相加再宣称现金翻倍。一笔真实代付100可形成loan100、同时明确支付已有费用100，现金仍100且费用只确认一次；退款100也可同时明确减少原费用和归还借款，现金仍一笔、两种业务贡献分列。未分配资金默认指义务资金口径，费用未归属另名显示；选择器按操作kind给对应可用额。目标义务可结额=original_amount−三类适用现金/非现金结算。票据可用额=original_amount−sum(ticket_use,ticket_offset)，不可再减offset第二次。expense付款上限按原额减已付份额（来源flow已支付份额同计）；本次退款≤min(累计已付,原额)−已有退款；所有写入后的累计退款≤累计已付且≤原额。更正/删除付款或移除费用来源也校验最终状态，冲突时允许同次明确修正错误退款分配，真实receipt保留、不自动删钱。expense作为non_ticket来源时可用额=净费用−已用于该类冲抵额；其支付和冲抵是不同维度，不把它们相加再消耗一次费用。退款导致已有无票分配超净费用时须同次明确纠正分配，不自动截额。

同flow/目标/kind的现金分配一行，唯一(flow_id,item_id,kind)用于防同一分配重复；合并到已有行走CAS更正。同票据多次使用允许不同ID与日期，票抵多个目标分行。将一次ticket_use改为ticket_offset是PUT原ID及目标/版本，原占额不再扣第二次；反向纠错也仅改该记录。跨行可用额必须在同事务锁来源/目标后校验。

### 3.10 原生约束与初始索引

内部FK仅指cash.*，默认ON UPDATE/DELETE RESTRICT；清理专属关系用明确事务，不级联删除其他真实flow/独立事项。所有金额正数/有限值、NULL组合、日期、月份首日、版本正数和类型适用性用CHECK+NOT NULL；累计额度/启停/起算关系在锁内检查，不用CHECK伪装跨行SUM保证。

初始索引：flows(occurred_on,created_at,id)、(from_account_id,occurred_on,id)、(to_account_id,occurred_on,id)、task_occurrence_id；occurrences唯一(template_id,month)及(month,due_on,id)；settlements(item_id,occurred_on,id)、flow_id、source_item_id；items(origin_flow_id)、(type,origin_date,id)、(bill_label_id,origin_date,id)、ticket_source_id。deleted_submission_ids仅复合PK(entity_type,id)。查询SQL完成后用EXPLAIN核对实际使用和冗余；未证明需要不加GIN/分区/每列组合索引。FK不会自动创建引用端索引。

账单/账户/分类/模板有引用只停用，避免反复删除/重建身份。flow/item正文物理删除见§4；不加入soft-delete和第二活跃范围。保留已有其他模块的安全约束，不迁移普通银行表。

### 3.11 来源、可修改性和技术边界

- id/创建actor/created_at/来源kind不允许修改；系统version/updated_at由服务端管理。
- PUT白名单中未提供字段保持、null仅清空适用可空字段；无实质变化changed=false，空命令400。
- 配置姓名/名称更名仅改变显示，不改已有业务含义；OA名称快照只在重新选项目时更新。
- items原额/日期/来源更正必须验证所有剩余分配与受影响flow；origin_flow建立事项不能绕过flow单独更改来源金额，使用§5.5复合纠错。
- settlements可更正类型仅ticket_use↔ticket_offset和同类归属/金额/日期，不能把非现金直接变现金。删错记录再明确正确处理，不能保留隐藏兼容分支。
- task_snapshot不接受整包客户端覆盖；历史已落库月计划可通过明确adjust修正，但模板编辑不会改它。
- 不新增tenant、附件、OCR、导入、私有历史、成本模块、同步worker或通用幂等平台。精细字段覆盖已确认业务，不以表数少为由把金额/来源塞到备注。

## 4. 删除存储：已确认物理删除正文

删除有效flow、明确误录item以及错误settlement的业务正文，不设回收站/恢复接口/私有操作历史。删除后所有现金页面与汇总不再计入对应贡献；保留独立真实其他现金/义务。

最少身份表cash.deleted_submission_ids只有entity_type(flow/item)和id(UUID)，复合PK，不保存时间、金额、姓名、项目、账户或请求正文。flow删除及源专属item删除与其身份写入同一事务。独立item也能误录删除，需相同已删ID保护；settlement撤销的旧POST由仍存来源/目标的已递增版本拒绝，不机械给所有配置动作造历史。

具体失败场景：创建提交成功但响应丢失→另一会话删除→原创建延迟重试。删除主键后，主键/唯一约束不再记得它，版本随行消失；Git/类型/测试不保存运行历史，单次事务也不能证明以前是否创建。保留类型+ID即可拒绝旧提交，不需要hash、内容副本或事件系统。并发插入等待删除提交的细节见§5.2；items采用相同算法。

外部语义只有一套：首次删除200 deleted=true；同已删ID再次删200 already_deleted=true、此次影响数0；从未存在404；详情已删404；旧创建命中已删身份409 cash_submission_deleted；旧编辑/分配/认领404或明确冲突，不upsert、不换ID自动重建。授权先于存在性查询。

删除在线业务正文不等于销毁已有备份/PITR或物理磁盘历史；不删除主库/常规备份。最少ID不提供用户列表、业务恢复或全局历史。

## 5. 写事务、锁与一致性

### 5.1 通用约定

采用当前 repository 的短事务能力；写事务优先用 PostgreSQL 原生行锁、唯一约束和版本比较，不引入分布式锁。写事务可以使用 `READ COMMITTED` 加明确行锁；组合读使用现有短 `REPEATABLE READ READ ONLY`。

提交前网络读取与数据库事务分离：先授权/参数规范化和可能的重放查询，再完成必要 OA 校验，最后进入现金事务。事务内重新核对目标版本；只有selection新选/改选项目才复核允许阶段配置版本。existing_item仅验证现金事项，不请求OA、不依赖阶段允许集合；不在持有SQL行锁时等待OA。

统一锁顺序：阶段设置 → 分类/账单别名 → 账户 → 模板 → 月度处理 → 流水 → 事项 → 专属结算。每一层涉及多个对象时，均按稳定 ID 的固定升序取得锁；配置类、账户、occurrence、flow、items 和结算采用同一原则，不能按页面选择顺序或业务 from/to 顺序加锁。例如 A→B 与 B→A 两笔互转都先锁较小 ID 账户，再锁较大 ID 账户，避免反向互转形成死锁。只锁本次真正涉及的记录，不全表锁；任何命令不得先锁后层再回头锁前层。为计算删除影响进行的事务外读取只是定位提示，进入事务锁定后必须重新确认关系和版本。

若发现关系集合已经改变而需要加入更早层的锁，返回 409 要求刷新，不能临时逆序加锁或无限自动重试。账户启停/起算规则需与账户更正互斥时，锁相关账户；不以牺牲正确性换速度，之后测量争用。

锁强度也必须明确：阶段配置/分类/模板资格仅需稳定读取时采用共享行锁，允许不同现金请求并行读取，但阻止事务期间改配置；真正修改的flow、occurrence、items、settlements用更新行锁。账户仅检查启停/起算资格采用共享行锁；允许负余额，不将所有同账户收付独占串行化；账户配置修改用更新锁。只锁本命令必要行；涉及个人loan或个人起算的动作才额外共享/更新锁settings，其他无项目且无个人起算依赖的操作不统一锁它。不得为方便将所有收付都排在同一全局独占锁上，锁模式与次序用真实PG并发测试核验。

### 5.2 新建手工流水

1. route 先鉴权，再校验严格 DTO；actor 从 session 获取。
2. 用稳定 ID 查询是否已有创建结果/已删除身份。同内容未修改结果可返回；冲突明确拒绝，不先依赖 OA。
3. 明确project_mode：selection有项目时只读OA真项目/阶段及本地允许配置版本，无项目不查OA；existing_item读取锚点事项的本地项目ID/名称快照并定位同项目结算目标，不请求OA，不能从失败的selection自动切换过来。
4. 开始现金事务，按锁序校验账户/分类、适用的配置版本、目标ID与版本；existing_item须确认锚点仍是本次正额结算目标、类型/方向/额度可办理、全部目标同项目。再次检查删除身份，消除前置读取竞态。
5. 保存一个flow；selection可按明确请求建立related_items/origin_items/allocations，existing_item只允许已有事项的现金allocations，禁止夹带新事项/补本金/改变项目。调用同事务内部方法，任一失败整笔回滚。来源由入口确定为manual。
6. 提交后返回新版本。没有全局 audit、job、报表副本或后台补偿。

同 ID 的并发插入明确采用仅针对主键的 `INSERT ... ON CONFLICT (id) DO NOTHING`，检查是否实际插入，再进入两个明确分支：

- 实际插入：继续本次新建的必要关联，并执行下面的最终已删除 ID 复查；通过后才能提交。
- 未插入：在下一条语句读取并按需锁定当前对象，按规范化字段及版本判断同次已有结果/不同内容；不重复建立事项或分配。若此时已被删除，则查询已删除身份并返回已删除冲突；当前事实已经变化但不能认定同次成功时返回明确冲突，不重新插入。

该写法不触发“捕获主键唯一异常后，继续在已 aborted 事务里 SELECT”的错误路径。其它约束/数据库异常仍按事务边界整体回滚后映射明确错误，不能一律吞异常继续读写。禁止 `ON CONFLICT DO UPDATE` 将重复创建变成改账，也不使用忽略所有冲突的宽泛语义。

物理删除中，**插入前查询已删除 ID 仍不充分**：删除事务已经删除原行但尚未提交，重试 INSERT 可能在唯一键检查处等待，删除提交后 INSERT 反而成功。最少闭环如下：

1. 删除原行与保留 ID 必须同事务提交。
2. 创建沿用 `READ COMMITTED`；实际 INSERT 成功后，使用下一条语句、在本次提交之前再次读取该已删除 ID。
3. 若删除 ID 存在，整笔创建事务回滚（连同任务/分配），返回 `cash_submission_deleted`；不能仅删除新 flow 后继续提交其他关联。
4. 因为插入成功已经越过原主键等待，导致其成功的原删除事务此时已提交；`READ COMMITTED` 的下一条读取能看到同事务写入的删除 ID。如果创建先提交，随后删除则正常删除该已提交事实。因此不需要额外锁平台或 hash。

最终重查不能复用插入前快照、进程缓存或使用事务级旧快照的查询；真实 PostgreSQL 并发测试必须精确覆盖“重试 INSERT 等待原 DELETE 提交后成功”的交错，而非仅顺序执行新增→删除→重试。

### 5.3 任务新建现金与关联既有现金

两条分支互斥，由请求明确选择，不通过有无金额字段猜分支。

| 分支 | 操作 | 必须不发生 |
| --- | --- | --- |
| `new_flow` | 月实例唯一建立/锁定 → 校验模板/月/版本 → 建一个任务来源 flow → 同事务必要结算 → 根据有效现金判断月处理状态 | 两笔 flow；task 已付但 flow 失败；内部 service 自行提交 |
| `existing_flow` | 月实例锁定 → 现有 flow 版本锁定 → 验证方向/账户/金额/认领情况 → 建立关联 → 复用已有结算事实 | 改来源为任务、再创建现金、再次冲减已有分配、模糊同额匹配 |

已有流水关联任务会修改关联，须递增 flow 和 occurrence 的版本。若已有相同关联且版本/目标状态对应同次已成功动作，可返回现状；若已被删、改认领或状态前进，返回冲突，不重新执行旧意图。

某手工 flow 已有结算时，确认任务只接入引用。若任务还需要额外分配，先返回当前分配与可分配额，用户明确调整，再按余额/事项约束提交；不能覆盖或重建原分配。允许部分支付时，累计只按每笔有效 flow 计一次。

首次确认重试的判断顺序必须先于空版本/CAS拒绝：对new_flow按稳定flow ID及目标template/month核验§2.2的已成功复合意图；成立就返回该flow与当前月状态，不再创建或重验已结束项目。对existing_flow只在当前目标关联与所提交预期flow版本+本次认领后的版本关系仍能证明同次成功时返回当前结果。已删或已发生后续改动则409/404，不以“现在看起来已付”证明是该请求成功。不能证明是重放时，才执行新动作的首次null/已有实例CAS；另一个flow ID的并发首次确认不得越过该校验。

没有flow身份的adjust/mark-unpaid/complete-check/reopen-check使用普通CAS：响应丢失后重复旧版本可返回409，前端GET核实当前状态并明确结果，不自动盖最新版本再提交。这里不承诺每种配置动作都返回第一次响应，不为此增加通用command表；即使反复点击也不能重复产生现金。

### 5.4 单笔删除：唯一命令

1. 读取当前目标及删除影响，确认界面显示日期、金额、来源与关联摘要。这个只读结果可能过时，不能替代执行校验。
2. route 提交 ID/预期版本。事务内按统一顺序锁账户、关联月份、flow 与相关事项；重新验证版本及关系集合。
3. 去掉目标 flow 专属的结算/用途分配；不触碰其他付款或独立非现金事件。
4. 物理删除flow正文，同时写入必要的已删除身份。二者必须同事务，不能删完后由后台补 ID。
5. 重新计算受影响事项/任务的状态；版本递增。金额若按事实查询则不再存第二份累计总额。仅由此 flow 建立的事项按第 5.5 节获批规则处理。
6. 成功一次提交；任何失败全部回滚。返回不含已删除正文的结果。前端关闭目标详情并重读本地现金视图，其他 Tab 的旧数据失效。

删除过去月份的收入/支出会改变之后余额，但不生成一笔反向现金“抵消”。互转删除同时移除两账户贡献。删除可以不依赖 OA 在线，不检查项目是否仍可新增；也不进入普通历史、全局任务、重置或报表重建链。

### 5.5 来源事项纠错：与flow编辑/删除同一命令

普通还款删除只撤本笔分配，原债务和其他真实flow保留。flow同时建立items时，按每个源事项明确处理：

| source action | 所需输入 | 同事务结果 |
| --- | --- | --- |
| correct_amount | item_id、expected_version、original_amount；跟随父flow新日期/项目 | 错本金1000改800、已还200保留，剩600；分配与来源份额仍须合法 |
| delete_false_item | item_id、expected_version | 错来源及仅由其建立的假义务删除；移除该假义务的现金还款分配，真实其他flow保留且显示未分配 |
| keep_independent | item_id、expected_version | 用户明确债务真实但此flow来源重复，解除origin_flow_id/origin_mode，保存真实原义务；不自动执行 |
| rebind_flow | item_id、expected_version、new_flow_id、expected_new_flow_version | 改绑明确正确现金来源并设origin_mode=linked，校验对应资金口径余量/方向/日期/项目，不新造现金 |

删除来源flow时不能用correct_amount保留仍指已删flow的item。没有后续且origin_mode=created的专属事项，普通删除确认展示将一起删除，无需二次选择。origin_mode=linked的既有真实loan或显式改绑expense删除来源时仅解除来源关系、两来源字段置null并保留事项，不能按有origin_flow就误删；费用解除付款来源仍须通过退款/支付最终额度校验。普通origin_items仅loan，不因此允许重复确认已有费用。有特殊更正意图再显式source_corrections。存在后续结算的事项由用户明确选择上述合法动作；不能按“有引用”一律禁删。

真实非现金记录不能跟着假债务丢掉：票据使用若实际只是使用，用户可将ticket_offset明确改为同ID ticket_use；确为别处抵债时明确重分配；确为误录可明确remove。无票真实冲抵无正确目标时明确冲突，保留原事务，不造目标/截额。真实expense等独立事项只解除错误展示归属，不删除其费用事实。

统一命令使用可选source_corrections[]和settlement_changes[]（§8.2），包含实际旧/新对象预期版本，一次事务完成。更正本金到100而既有还款200，需要同次明确移除/调整错误分配；不自动把200截100或产生负债。没有真实合法方案时返回具体冲突和原状态，不返回成功后让用户修数据库。

### 5.6 编辑、非现金和独立事项误录

flow可改字段见§3.5，未变项目不查OA，变项目需新资格校验；owned items日期/项目按明确来源一起改，金额按source_corrections显式给份额。与独立历史item项目不符时须先明确纠正，不能替它静默换项目。改变flow实际日期同步本flow现金分配日期；相关目标发生日、账户起算和任务方向均重验。

settlement更正/移除锁旧新flow、来源/目标item，按§5.7校验版本。ticket_use↔ticket_offset在原ID修改，不重复消耗票据；撤误用释放来源可用额。独立非现金动作不动现金余额；分配改变不得改flow.amount。真实退款只能新增receipt及expense_refund，不能用撤销真实付款代替。

独立item误录可通过items/{id}/remove删除：无来源flow且无后续，删正文+保留item已删身份；有后续沿用明确settlement_changes，保留真实现金，独立真实非现金必须纠正后再删；owned item则通过所属flow纠错入口，不能绕过来源金额约束。公司应收引用ticket_source、expense展示归属引用义务时，删除错误父项需显式解除/更正关联，真实子事项仍保留。不建恢复/私有历史。所有更正失败整体回滚。

settlement旧创建重试：先识别仍有效同ID/同意图，否则必须验证请求中的旧来源/目标/flow版本；移除已使这些对象version变化，故旧创建不能复活。删除item的旧创建另有§4纯ID保护。不用服务端新读版本代替调用者，不增加通用command表。

### 5.7 命令、受影响对象及版本传播

统一原则：锁全部受影响旧/新对象，校验请求中该操作涉及的预期版本；同一已存在对象在一次事务内只加1，不按分配行数加多次。刚创建对象本次最终为1。派生汇总没有自己的永久版本/表；重新查询得到当前事实。

| 命令 | 需要核对/受锁对象 | 递增范围与不改变的内容 |
| --- | --- | --- |
| 编辑flow日期/金额/账户/项目/内容 | flow及涉及账户；有关联则occurrence、分配、旧/新目标items；源事项按§5.5 | flow；影响任务展示/完成时occurrence；实际影响的items/settlements。账户余额是查询值，不为每笔钱更新账户配置version |
| 新增现金分配 | flow、目标item，必要occurrence | 已有flow、目标item；任务依赖该分配时occurrence；现金amount不变 |
| 更正/移除现金分配 | 原settlement、旧/新flow、旧/新目标item，相关occurrence | 全部实际变化的既有flow/items/settlement与受影响occurrence；旧新两端都处理，不能只验新目标 |
| 新增/改/撤非现金冲抵 | settlement、旧/新来源item和目标item | 相关items/settlement；现金flow和账户余额完全不变 |
| 认领已有flow到任务 | flow、目标occurrence；若已有其他任务关联需按批准规则处理 | flow+目标occurrence；不重建既有settlements；不更改source_kind |
| 删除flow | flow、关联occurrence、源/目标items、专属分配 | 留存关联对象版本递增；被删对象物理删除并保存必要ID；其他不相关flow保持 |
| 更正item | item；若改变来源flow或分配约束，相关旧/新来源和目标依统一锁序 | item及确受影响的关联对象；不得把改显示名变成重计现金 |
| 调整月处理/核对 | occurrence；首次还校验template.version | occurrence；不修改template/flow的实际日期或金额 |
| 改账户/分类/模板/阶段设置 | 对应配置行 | 只改其配置version；不批量改写历史flow；下一次相关新选择在事务中复核 |

分配更正/移除命令必须包含涉及flow、来源item、目标item的预期版本，详情/选择器返回这些版本；缺少必需版本400，不用服务端刚读的新版本替调用者覆盖。若更改归属涉及一组旧/新对象，使用有界的明确ID/version集合，而不是通用锁令牌或冻结合同。

## 6. 查询、报表与金额定义

### 6.1 现金账户金额：已明确部分

对账户 A，一笔有效 flow 的账户变动：转入 A 为 `+amount`，转出 A 为 `-amount`；其他账户为 0。互转在全池合计为 0。

```text
查询期初 = 经确认的起算金额 + 起算时点后、查询开始日前的有效净变动
查询期末 = 查询期初 + 期间流入 - 期间流出
全池本期现金收入 = receipt 金额合计
全池本期现金支出 = payment 金额合计
分账户流入/流出 = 对该账户的现金变动，包含 transfer，明确标注互转部分
```

期初表示起算日记账开始前余额，当日flow参与之后净变动；全接口统一此口径。删除后所有公式只使用剩余有效事实。

期间边界不能遗漏。设账户起算日O，查询开始S、结束E（日期均含端点）：

- `E < O`：没有该账户该期间的已知余额，返回未起算/不适用，不返回0或未来期初；不能把7月15日设的1000当成6月余额。
- `S < O <= E`：只能描述从O开始的已知记录。返回 `opening_balance=null`、`coverage_start=O`、`coverage_state=starts_during_period`，单列起算余额；期末按O以后有效事实计算，期初金额不作为期间收入。允许显示这种部分期间，并明确覆盖提示，不静默改查询日期或用未来余额倒填。
- `O <= S <= E`：期初为起算金额加 `[O,S)` 净变动，期间收付为 `[S,E]`，期末为两者合计；以批准的起算日开账前口径为前提。
- 多账户起算不同时逐账户给coverage；没有完整已知期初就不能展示一个无说明的全池完整期初。已确认人民币两位；多账户期初覆盖不一致时仍不能把部分已知额冒充完整总期初。

负余额如实显示并给出核对警示，不阻止真实收付、不加审批、不造平衡收入。往期更正改变其后余额，由全账序查询重算；不新增月快照或只改屏幕当前页。

业务“真实花销”不是 `payment` 的别名；还借款、垫付、账户互转不能直接当费用。债务余额不是账户余额，不能把 Excel 个人欠款公式拿来做现金余额。

### 6.2 逐笔余额与筛选合计

- 固定账序建议为 `occurred_on, created_at, id`；同日先后需要用户可指定时再增加明确业务顺序字段，不依赖随机 ID 冒充真实付款先后。
- 逐笔余额先按完整账户账序计算，再应用项目/人员/关键词等显示过滤和分页；不能用当前页或匹配行的累计数作为真实账户余额。
- 按金额排序只改变列表顺序，不重新定义账序余额。必要时列名说明“记账顺序余额”。
- 跨账户列表如果没有选择单一账户，不显示一个含糊的“余额”；可返回每账户汇总及本行涉及账户的余额，最终列布局由 UI 定案。
- `summary.account_balances` 与 `summary.filtered_totals` 分开。账户余额只受账户和期间边界影响；筛选合计采用当前筛选条件，不能两者互换。
- 内部转账全池收入/支出不重复膨胀；转入/转出分别属于账户视角。

### 6.3 报表事实、行粒度与固定金额定义

| 查询 | 行粒度/事实 | 金额与排除 |
| --- | --- | --- |
| 现金流水 | 一flow一行，手工和任务全集 | 收/付/互转及余额；不因未入往来总表排除工资/房租 |
| 往来总表 | 一义务初建事件、每次相关settlement、明确归属该义务的expense事件 | source flow与初建item只一行本金；公司淡黄/外部蓝/个人新增橘/归还冲抵绿；普通独立费用不纳入 |
| 有票支付 | 一ticket_source一行，使用/抵债/公司回款下钻 | 提供额、已使用(含票抵)、其中票抵、明确应收及实际回款、剩余可用票额分别列 |
| 刘树刚账 | bill_label_id稳定矩阵行；无账单的明确个人借款为一个标识为non_bill的展示分组 | 按实际代付/新增借款月份，is_opening不再计本金；公司ETC等非个人义务不纳入 |
| 历史项目选项 | cash flow/item已有OA ID+名称快照去重 | 与OA当前选择器分开，结束/源删除仍能查历史 |

往来五列：non_ticket_offset_amount=无票/明确非现金冲账；repayment_amount=loan的cash_repayment分配；reimbursement_received_amount=company_collection；ticket_offset_amount=ticket_offset；real_expense_amount=明确归属该往来的expense原额减expense_refund。这五列不能横向相加形成现金或剩余债务。费用归属通过expense.related_obligation_id明确指定；不按同银行、同月、同金额猜配。源flow带loan并独立费用已有时，不再把loan本金算真实花销。

初建义务行original_amount仅该次原额，后续结算行该列null；source flow相应现金金额取该初建item的明确来源份额，不重复整flow。分配行只用分配amount；费用/费用支付/费用退款事件的cash_received_amount/cash_paid_amount为null，关联实际flow供详情查看，不把同笔代付再次计入往来现金列。总表这两列只汇总义务建立/归还/公司应收结算的资金份额，不冒称全部现金收入支出；全池收支始终看现金流水。expense_payment不再确认费用、real_expense_amount=null；expense_refund仅在费用事件显示负净费用，不自动当还本金，确有归还另显式分配同一flow。

同一flow 100分40/60：流表100一行，往来分别40/60；不同flow各100合计200。先按唯一事实ID/归属聚合，禁止JOIN放大或SUM(DISTINCT amount)按值去重。剩余义务按item去重后截至查询date_to结算，不能把每个事件行的余额再次相加。

个人年度未结=期初已知未结+本年新增本金+本年明确起算未结调整−现金归还−票抵−无票冲抵。is_opening记录只计起算调整、不计矩阵新增；起算以前未知不伪造完整历史。11月付款12月账单只入11月本金，bill_month=12月独立展示；无账单本金不挂假银行卡。个人子表按实际settlement.occurred_on过滤，账单月份只能作为额外属性/筛选。

### 6.4 查询实现步骤

1. route 校验页码、页大小、排序白名单、日期范围和 UUID；拒绝未知筛选值，不把未知状态静默忽略。
2. repository 开一个短只读快照，按日期/账户范围读取；rows、total、summary 从同一快照取得。
3. 采用集合 SQL 和有界批量关联读取；无逐行 OA、任务、事项查询。
4. 所有有效事实筛选一致应用于主表、子表、详情、汇总、历史选项；不得建一个遗漏删除条件的旁路接口。
5. 返回实际空集合才是 empty；数据库或 OA 故障不是空集合，也不是 0 金额。
6. 页面写成功后 GET 重新读取；不返回 read-model status、refresh job 或新 freshness 字段，不启动后台计算。

逐笔余额的具体查询顺序：先按账户和已知起算点聚合查询开始前净额，再在本期完整账户流入/流出账序上计算窗口累计；之后才应用项目/人员/关键词显示过滤及所选排序/分页。多账户互转在余额计算中展开两端贡献，在流水列表仍只保留一个flow ID；不先JOIN事项再累加现金。总数、筛选汇总和rows在同一短快照；它们可以是固定少量集合查询，不要求为了“一条SQL”写难维护的巨型查询。

详情也需有界：主对象+必要汇总一次读取；关联明细使用下文的cash列表查询和分页，不能一次塞入多年全部还款。删除预览只读总数和有界摘要，真正删除仍在一个事务处理全部实际关联，不能仅删预览首50条。每次写不会后台重建其他报表。

## 7. 月任务日期、状态与历史保留

### 7.1 日期与页内提醒

计划日=当月min(execution_day,该月末日)，这是用户已接受的显式规则，不是猜银行日期或隐藏fallback；允许adjust，实际收付日永远独立。提醒日=due_on−remind_days，上海业务日期，跨前月仍属原月。

remind_days初版0–31，超界400；调整due_on最多离归属月边界31天，明确输入范围，不自动移动节假日。按提醒窗口查询时覆盖可能提前的后续月份，再过滤真实remind_on；读取已有实例时不因模板变更丢掉当月调整。现金页进入/聚焦/日期变化重读；关闭页面不提醒，不建worker/全局badge/外部消息。

### 7.2 单一完成算法

数据库processing_state仅有pending/unpaid/checked的用户意图；API唯一展示state按以下顺序计算：

| 条件 | state | 金额/说明 |
| --- | --- | --- |
| check且checked | completed | planned/actual均null |
| check且pending | pending | 无现金 |
| 收付actual=0、planned为空或有值 | pending | planned空另need_planned_amount=true；marked_unpaid按意图显示 |
| 收付0<actual<planned | partial | 剩余计划=planned−actual |
| 收付actual>=planned | completed | is_over_plan=(actual>planned)，超出額单列，不截实际金额 |

收付确认必须有正planned_amount；首次可同请求填写目标与本次实际，已有目标修改需明确adjust；actual>0时planned_amount必须保持正数，不允许清null/非正，否则400且原状态不变。actual为该月所有有效关联flow金额合计，一flow只计一次且不能归两个任务。超目标仍允许真实现金，债务分配上限独立约束。删任一flow后据剩余金额重算；零现金回pending，旧提交不补流水。

marked_unpaid只可在actual=0时设，不能盖掉partial/completed；办理后意图改pending，事实由amount决定。is_overdue=state!=completed且due_on<today；今天到期可单独显示is_due。日期越月不改month。允许核对误点reopen；模板/计划额/实际额不建立多套paid/done字段。

### 7.3 模板变更时保存旧月，不加调度器

1. 新建模板从当月/未来明确生效，禁止追造应用使用前任务；所有GET无写。
2. 月查询读取已存instances，再对当前模板有效区间生成缺失虚拟月，按全匹配集合计数/分页。逾期查询范围从真实生效月到今天，不只查已点击过的月份；SQL集合生成，不在浏览器补月。
3. 编辑/停用模板：先在同一现金写事务锁模板，把旧enabled=true的旧生效区间∩截至当前月区间内缺失月份按旧快照集合插入；已存在的任何实例都不覆盖。
4. 普通模板编辑从下月（或原本更晚的首月）生效；当前月由上一动作保存旧值，要改当月走adjust。旧effective_to已过则不把结束后月份补出；延期需明确新起始月份。
5. 停用作用于下月及以后，本月和之前应保留的月份已保存；enabled=false后查询仍返回所有已有实例。未来已经明确单独调整的实例不删除，显示原计划，用户可继续处理。
6. 已停用模板的编辑不补停用期间；重新启用明确当月/未来生效，保留旧实例，新区间不覆盖旧记录、不追补暂停月。新旧区间不存在的月不合成待办。
7. 首次办理虚拟月以template版本+月唯一键+null occurrence版本创建；已被模板变更物化则409重新读取，不能空版本覆盖旧快照。原flow重放判断仍优先于此CAS，见§5.3。

模板写操作只物化必要待办/快照，不生成现金；一个模板一次集合SQL，范围由旧真实启用起止限定，无逐月网络I/O。提醒/逾期使用分页与有界时间参数；长期未改模板的跨度用实测判断短事务成本，不静默漏月或偷偷转后台补偿。模板创建/更正日期的上限为数据库合法日期与上述生效规则，不用任意多年回溯开关。

## 8. API 详细草案

### 8.1 公共语义

下面 `/api/cash/...` 是应用逻辑路径；部署通过现有前后端代理，不让客户端硬编码另一套生产前缀。所有 API 都属于现金页，先认证授权，再读取目标数据。全部写动作仍是真实 mutation，只按精确现金 route 排除全局操作历史。

分页技术建议：默认 50、最大 200；`page` 从 1 开始；超界参数 400，不静默钳到另一页。删除当前页最后一行后，前端依新 total 请求最后一个有效页，不由后端悄悄返回别的 page。默认月、支持年，任意跨度须有明确上限。

金额输出统一字符串；`null` 表示不适用/未配置，不变成 0。成功写返回持久化对象版本；错误沿用现有 `{"error": code, "message": text}` 外壳，保留稳定错误码和用户可理解的消息，不重复建立第二套错误框架。该格式已在现有 `routes_turnover_ledger.py` 核验；只复用格式，不复制其业务依赖或内存 fallback。本文现金错误码为拟定值，实施时一次对齐。

不为一处调用创造通用 CRUD 注册器；下面路径对应具体动作。请求不接受 `actor`、客户端余额、客户端已结算累计或客户端来源伪装字段。

### 8.2 流水、复合纠错与报表

| 方法/路径 | 输入 | 输出 |
| --- | --- | --- |
| GET /api/cash/flows | date_from/date_to或明确父item_id/task_occurrence_id；account_id/project_id/category_id/kind/person/source/keyword/sort/order/page/page_size | rows,summary,pagination；选择器另见§8.7 |
| GET /api/cash/flows/{id} | ID | flow,allocations,allocation_count,allocations_has_more,task,delete_impact |
| POST /api/cash/flows | FlowCreate | 首次201/同次200：flow,related_items,origin_items,allocations,version；既有origin_items返回新版本 |
| PUT /api/cash/flows/{id} | expected_version+§3.5可改字段+可选source_corrections/settlement_changes/item_reference_changes/expected_related_versions | flow,version,changed,affected_counts,affected_items,affected_tasks,affected_preview_truncated |
| POST /api/cash/flows/{id}/delete | expected_version+必要source_corrections/settlement_changes/item_reference_changes/expected_related_versions | id,deleted,already_deleted,affected_counts,affected_items,affected_tasks,affected_preview_truncated |
| POST /api/cash/flows/{id}/unlink-task | expected_version,expected_occurrence_version | manual flow/occurrence新版本；不改创建来源/分配；monthly_task拒绝 |
| GET /api/cash/reports/turnover | date_from/date_to,ledger_group,counterparty,project_id,category_id,state,keyword,sort/order/page/page_size | 固定TurnoverRow及summary/pagination |
| GET /api/cash/reports/ticket-payments | date_from/date_to(按提供日),ticket_provider,project_id,state,keyword,sort/order/page/page_size | TicketRow及summary/pagination |
| GET /api/cash/reports/personal | year,view,bill_label_id,project_id,bill_month?,keyword,sort/order/page/page_size | view=matrix/cash_repayments/ticket_offsets/non_ticket_offsets；只返回当前view |
| GET /api/cash/reports/project-options | date_from/date_to,keyword,page/page_size | 本地历史rows/pagination，不查OA |

FlowCreate明确字段：id、occurred_on、kind、amount、from_account_id?、to_account_id?、category_id?、project_mode、oa_project_id?、project_item_id?、expected_project_item_version?、person_name?、content、remark?、related_items[]?、origin_items[]?、allocations[]?。必填/可空/适用性见§3.5；不接受source_kind/actor/余额/名称快照。related_items是唯一数组形状，不同时保留旧单事项兼容分支。

project_mode必填，严格区分两种创建上下文：

| 模式 | 输入和验证 | 项目来源/禁止项 |
| --- | --- | --- |
| selection | oa_project_id可空；不接受project_item_id/expected_project_item_version；非空新选项目须当前真实非结束且阶段获允许 | OA只读确认；不能用普通项目状态或历史快照替代失败校验 |
| existing_item | 必需project_item_id与正数expected_project_item_version；必须receipt/payment、至少一条既有事项现金分配，锚点实际参与正额分配且其版本与allocation一致；全部目标项目相同，null不是通配 | 服务端从锚点复制本地项目ID/名称；不接受客户端oa_project_id、related_items、origin_items，不允许transfer；不请求OA/阶段配置、不改变项目 |

existing_item允许已结束、OA源删除或暂不可用的历史项目真实结算；未分配的真实超额现金仍按已有金额规则明确显示，不自动生成新义务/费用。不得把“必须有真实锚点结算”扩大成所有现金强制全额分配。project_mode/锚点字段只用于本命令校验，不新增DB列或另一条持久化链。项目在该结算表单只读；将来更正流水归属仍走明确改选和关联纠错，不永久冻结流水。任务new_flow直接复用本DTO。

related_items仅loan/expense，字段id/type/origin_date/original_amount/content及§3.8类型条件字段；origin_flow_id由服务端设置，日期/项目必须与父一致。新company_receivable/ticket_source走独立items，不由现金入账偷偷造应收/票据。现有费用只用allocations关联，不能重复创建。

origin_items=[{item_id,expected_item_version}]仅用于已有真实loan迟录现金：无origin_flow、非opening、日期/方向/项目匹配才可绑定本flow并设origin_mode=linked，保留原ID/原额/实际日期，不把未来账单改成已发生本金；各维度额度照常计入。与related_items不得重复ID。已有item版本本事务+1，新flow仍version1；复合重放包含绑定意图，不以旧expected版本重做绑定。

allocations每项为id,item_id,target_is_new,expected_item_version,kind,amount,remark?；target_is_new=true仅可引用本次related_items且expected_item_version=null，否则false且版本正数。flow_id/occurred_on由服务端绑定，禁止source_item_id。每一现金分配遵守§3.9；分别校验义务资金与费用口径，不把二者相加成现金额度；related_items+origin_items+allocations合计最多100条，不拆成半事务。

source_corrections每项使用§5.5四种action的严格字段白名单。

需要删除错误父事项并保留真实子事项时，窄字段item_reference_changes=[{item_id,expected_version,related_obligation_id?,ticket_source_id?}]只更正这两种展示/来源引用，未提供保持、null显式解除，新目标须在expected_related_versions.items给版本。与源删除同事务，不给任意item PATCH平台；禁止改变原额/业务类型。普通无子引用删除不必提交空表。
settlement_changes每项为{id,expected_version,action:remove/update,fields?}，update仅§3.9可变字段，remove不带fields。expected_related_versions固定为{flows:[{id,version}],items:[{id,version}],occurrences:[{id,version}]}，包含所有需要用户更正的旧新对象、所属任务；空类用[]，省略必要版本400。源删除自动释放错误现金分配时可按预览明确的源义务版本校验整组，其下分配变更会传播item.version，不要求用户逐条抄出成百条自动解除项。独立非现金选择须逐项明确，最多100项更正；超范围先明确分批纠正仍有效记录再删源，不提交半个删除。

删除预览复用详情，不新建delete-impact服务或签名。普通无冲突删除只expected_version；有源纠错再提交必要字段，重复已删ID不重放纠错副作用。权限先校验，错误400/404/409/503见§8.6。

### 8.3 任务

| 方法/路径 | 输入 | 返回/效果 |
| --- | --- | --- |
| GET/POST /api/cash/tasks | GET enabled/kind/keyword/sort/order/page/page_size；POST §3.6可写列+id | 模板rows/pagination或template/version |
| PUT /api/cash/tasks/{id} | expected_version+§3.6白名单 | template/version/changed；旧月物化与未来变更一个事务 |
| GET /api/cash/task-occurrences | month或reminder_from/reminder_to或overdue_as_of三选一；template_id/kind/state/keyword/sort/order/page/page_size | 已有+虚拟rows/summary/pagination；state用§7.2唯一枚举 |
| POST /api/cash/task-occurrences/adjust | template_id,month,expected_version或首次null；首次expected_template_version；due_on?/planned_amount?/note? | occurrence/version；已有现金改目标只改计划，不改实际 |
| POST /api/cash/task-occurrences/confirm | 同月身份/版本；mode=new_flow/existing_flow；目标尚空时planned_amount；new_flow=FlowCreate或existing_flow={flow_id,expected_flow_version} | occurrence,flow,version；顶层version属occurrence，flow有自身版本 |
| POST /api/cash/task-occurrences/mark-unpaid | 同月身份/版本、note? | occurrence/version；actual>0时409，不掩盖部分办理 |
| POST /api/cash/task-occurrences/complete-check | 同月身份/版本、note? | check完成，无flow/settlement |
| POST /api/cash/task-occurrences/{id}/reopen-check | expected_version | check待核对，无现金 |

GET提醒窗口最多62天、overdue_as_of不得晚于上海今天；服务端对已有due调整及当前模板有效区间计算，不只读当前月。现有历史实例不因enabled=false消失。首次动作null版本仅在月份尚未落库时可用；原flow重放识别优先于月CAS，不能新flow绕过。check/收付命令用错类型400。

new_flow复用同事务写原语，source_kind由入口设monthly_task。existing_flow只认领同方向已有现金，不改来源、不重复现有分配；同笔可全额计该任务实际，但现金可分配余额独立计算。金额未知首次同表单定目标；已知月目标不能在confirm悄悄改，需明确adjust。未办理意图动作丢响应重试旧版本409+GET，不加通用命令存储。

### 8.4 事项、分配与更正

| 方法/路径 | 输入 | 返回/副作用 |
| --- | --- | --- |
| GET /api/cash/items | type/ledger_group/counterparty/project_id/bill_label_id/bill_month/origin_date_from/origin_date_to/is_opening/has_bill_label/keyword/purpose/sort/order/page/page_size | rows/pagination；purpose=list/settlement_target/settlement_source，选择上下文见§8.7 |
| GET /api/cash/items/{id} | ID | item,amounts,settlements,settlement_count,settlements_has_more；精确类型金额 |
| POST /api/cash/items | id+§3.8适用业务字段；关联既有item时其expected_version；期初历史项目按§3.8验证真实OA资料 | item/version；独立事实不生成现金，期初不伪装本期新增 |
| PUT /api/cash/items/{id} | expected_version+可更正字段+必要settlement_changes/item_reference_changes/expected_related_versions | item/version及有界影响；owned事项来源改动走flow |
| POST /api/cash/items/{id}/remove | expected_version+必要settlement_changes/item_reference_changes/expected_related_versions | id,deleted,already_deleted,affected_counts及有界关联摘要；owned从flow纠错 |
| GET /api/cash/settlements | item_id/source_item_id/flow_id至少一个；kind/date范围/sort/order/page/page_size | rows/summary/pagination；明确父对象可查全历史并分页 |
| POST /api/cash/settlements | id,kind,amount,occurred_on,remark?；适用item_id/expected_item_version、flow_id/expected_flow_version、source_item_id/expected_source_item_version | settlement及实际受影响版本，不再创建flow |
| PUT /api/cash/settlements/{id} | expected_version+更正字段+expected_related_versions | settlement及旧新对象版本；use→offset只改本次 |
| POST /api/cash/settlements/{id}/remove | expected_version+expected_related_versions | removed=true及受影响版本；物理删误分配，不删真实flow |

无目标ticket_use的item_id/expected_item_version必须null，source_item必有；不能为了统一接口造假目标。独立非现金金额永不进入cash流接口。已删独立settlement重复remove，若无存续行返回404，客户端重读来源/目标确认；不承诺所有动作都保存首次响应。其旧POST必须因原相关版本变化或已删item身份而失败，不能使用新版本兜底。

### 8.5 设置与OA

| 方法/路径 | 输入 | 返回 |
| --- | --- | --- |
| GET/POST /api/cash/settings/accounts | GET enabled/keyword/sort/order/page/page_size；POST id/name/kind/opening_date/opening_amount/enabled?/remark? | rows/pagination或account/version |
| PUT /api/cash/settings/accounts/{id} | expected_version+§3.2可改列 | account/version/changed及起算影响提示 |
| GET/POST /api/cash/settings/categories | GET group/enabled/keyword/sort/order/page/page_size；POST id/name/group/enabled?/remark? | rows/pagination或category/version |
| PUT /api/cash/settings/categories/{id} | expected_version+name/enabled/remark；无引用时才可group | category/version/changed |
| GET/POST /api/cash/settings/bill-labels | GET enabled/keyword/page/page_size；POST id/bank_name/label/enabled? | rows/pagination或bill_label/version |
| PUT /api/cash/settings/bill-labels/{id} | expected_version+bank_name/label/enabled | bill_label/version/changed；不改变历史归属身份 |
| GET/PUT /api/cash/settings/personal-opening | PUT expected_version,opening_date（合法日期，不可在有个人事项时清空） | opening_date,version,changed；更正期初日期影响范围明确 |
| GET /api/cash/projects | purpose=all/selection,keyword,stage_code?,selectable?,page/page_size | rows,stages,total,page,page_size,read_at,selection_settings_version,configured |
| GET/PUT /api/cash/settings/project-selection | PUT expected_version,allowed_stage_codes | version,allowed_stage_codes,configured；PUT另有changed |

OA rows精确形状id/code/name/stage_code/stage_name/selectable/unavailable_reason；code或阶段缺失允许null，源缺必需ID/name则明确源格式错误而不是发明项目。stages[{code,name}]来自完整权威字典，不从当前分页去重。unavailable_reason=ended/stage_not_allowed/stage_missing/stage_unknown，可选时null；源故障503而非不可选项目或空集合。

all包含结束/未知，selection只可选；selection和selectable=false冲突400。全源范围过滤后计数分页，read_at只是读取时刻。固定结束编码必须实际核实，禁止硬编码用户估计或UI名称。无OA项目/阶段修改端点。

selection中的新选/改选项目由OA owner批量只读验证，在现金事务外完成；父flow、owned items及分配目标必须同项目，null不是跨项目通配。服务内收集有界去重ID集，用本地集合操作，不加hash指纹；事务内校验同一允许集合版本。关联历史未改项目不重新校验新增资格。R7的existing_item结算只沿用本地既有事项项目，OA不可用/项目已结束不阻断真实结算；不能自由新选该项目、混项目或带入新事项。期初非现金义务按§3.8从all只读识别历史项目，只核实真实身份，不按新增阶段允许集判断；它不是FlowCreate。不以普通completed override或财务项目缓存替代OA。

### 8.6 最少示例与错误

下面金额和 UUID 均为虚构说明，不是可直接发送到当前 App 的请求，字段适用性按§3。

手工无项目付款输入示例：

```json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "occurred_on": "2026-09-07",
  "kind": "payment",
  "amount": "100.00",
  "from_account_id": "22222222-2222-4222-8222-222222222222",
  "category_id": "33333333-3333-4333-8333-333333333333",
  "project_mode": "selection",
  "content": "虚构付款示例"
}
```

无来源纠错的普通删除输入只需 `{ "expected_version": 3 }`；成功结果形状为：

```json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "deleted": true,
  "already_deleted": false,
  "affected_counts": { "tasks": 0, "items": 0, "settlements": 0 },
  "affected_tasks": [],
  "affected_items": [],
  "affected_preview_truncated": false
}
```

编辑输入示例 `{ "expected_version": 3, "remark": "修正说明" }`；服务端只修改获准字段并返回版本 4，不因缺字段重设账户/金额，不在该请求中重新生成现金。

| 状态 | 错误类别候选 | 页面应做什么 |
| --- | --- | --- |
| 400 | `cash_invalid_input` | 指出具体字段，保留表单；不能把未知选项换默认 |
| 401 | 现有未登录语义 | 按现有 session 处理并清空现金敏感内存 |
| 403 | 现有页面不可用语义 | 不展示现金数据，取消旧请求 |
| 404 | `cash_not_found` | 关闭/提示对象已不可用，不恢复旧详情 |
| 409 | `cash_version_conflict` | 提示数据已变化，刷新后重新确认，不自动覆盖 |
| 409 | `cash_submission_conflict / cash_submission_deleted` | 同 ID 不同内容或已删除旧提交；不自动重建 |
| 409 | `cash_project_selection_changed` | 项目阶段/允许配置变化，重新选择；不改用普通项目 |
| 409 | `cash_allocation_conflict` | 额度/认领/来源不再匹配，显示具体矛盾 |
| 503 | `cash_dependency_unavailable` | DB/OA 不可用分区提示；历史账不因项目服务故障变空 |

错误明细只含必要字段名、当前版本和安全提示，不含 SQL、DSN、OA 原始对象、现金完整 payload。具体 OA 不存在与源权限失败分别处理，不能都装成“没有项目”。

### 8.7 响应字段、选择器和下钻闭环

以下DTO使用§2.1类型和§6金额定义。客户端必须区分缺字段（契约错误）、null（明确不适用/未知）和"0.00"（已知零），不以 `value ?? 0` 掩盖错误。普通银行DTO不扩展、现金DTO不继承它。

**分页与公共对象**

| 对象 | 明确形状与含义 |
| --- | --- |
| pagination | `page:integer>=1,page_size:integer,total:integer>=0`；total是全部匹配行，不是本页条数；超出最后页返回该请求页的空rows和真实total，不自动换页 |
| account reference | `id,name`；历史停用账户仍能解引用；列表无此端账户时整个引用为null |
| category reference | `id,name,group`或null；字典当前名称，不是自动分类结果；同一含义显示字典当前名称，换业务含义新建类别 |
| project reference | `id,name_snapshot`或null；现金历史只用本地名称快照，不携带OA原始记录或今日资格 |
| task reference | `occurrence_id,occurrence_version,template_id,month,title,kind`或null；title/kind来自当月快照，不用今日模板改写历史；source_kind与此关联分别展示 |

**现金行/详情**

`FlowRow`固定列：`id,version,occurred_on,kind,amount,from_account,to_account,category,project,person_name,content,source_kind,task,income_amount,expense_amount,account_running_balance`。person_name可null；收入行income_amount=amount、expense_amount=null，付款反之，互转二者null并独立显示amount。account_running_balance仅明确选定单账户时有值；混合账户列表为null。它按§6.4完整账户账序计算，不是筛选行累计；同一互转flow对不同单账户各有其对应账序余额。

详情中的`flow`在同一FlowRow基础上增加 `remark,created_by_account,created_by_name,created_at,updated_at`，不把created_by_name缺失渲染为虚构名字。`allocations`为下述SettlementRow最多20条预览，另给 `allocation_count,allocations_has_more`；完整子表GET settlements?flow_id。详情顶层`task`可复用同一引用，不另做不一致的当前状态计算。

`delete_impact`建议字段：`flow_version,task_count,item_count,settlement_count,source_owned_item_count,tasks,items,preview_truncated`。tasks/items各最多20条，元素只含id/version/title或content及必要纠正说明。是否需按§5.5处理来源事项用明确 `source_correction_required:boolean` 表示；它是业务纠正提示，不是按“有关联”统一禁删。真正命令重新读取全部关系，不信任预览。

删除响应`affected_counts`是本次实际处理的tasks/items/settlements数量；`affected_tasks/affected_items`各最多20条必要ID/version/状态摘要，`affected_preview_truncated`说明是否省略。前端统一让现金局部视图重新GET，不靠这两个数组逐表打补丁，所以不会因摘要截断漏刷新。删除重试只确认已删除且不再产生副作用，返回本次影响数0，不伪造首次完整影响或增加删除历史表。

**现金查询汇总（每次与rows同快照）**

| 字段 | 结构/公式范围 |
| --- | --- |
| `summary.period` | `date_from,date_to`，明确用户请求区间 |
| `summary.filtered_totals` | `flow_count,income_amount,expense_amount,transfer_amount`；按全部显示过滤匹配flow的唯一ID统计，不限当前页，不把transfer加到池外收支 |
| `summary.account_balances[]` | 每项 `account_id,account_name,opening_date,coverage_state,coverage_start,opening_balance,balance_at_coverage_start,period_inflow,period_outflow,ending_balance`；按账户/期间，不受人员/项目/关键词过滤影响；停用但在范围内的账户不丢失 |
| `coverage_state` | complete/not_started/starts_during_period；complete时opening_balance为请求起点余额，balance_at_coverage_start与之相同；not_started时金额均null；starts_during_period时opening_balance=null，其余只描述从已知起算点起的范围，明确提示部分期间 |
| 多账户总金额 | 已确认人民币，按同一已知覆盖范围求和；不同起算覆盖范围必须说明，不把局部覆盖总和冒充完整期间总额。未批准多币种，不预建汇率/折算字段 |

account_balances按本次账户选择范围返回：选择一个只返回一个；全账户视图汇总含各已配置账户。账户规模若实测使整组响应过大，再用独立分页账户查询配合显示，不先造余额快照。没有一个“未配置账户”的虚构余额行。

**已录现金/事项选择器**

沿用GET flows，新增可选`purpose=list/task_link/settlement`，默认list是接口的明确技术默认，不是业务fallback。task_link必须带 `template_id,month`，目标已有实例按唯一键解析；settlement必须带 `item_id,settlement_kind`。互斥/缺失上下文400；相关对象不存在404。选择器在FlowRow增加 `allocated_amount,available_amount,selectable,unavailable_reason`，查询还返回目标当前版本。金额来自§3.9同快照的相应口径，含origin_flow关联items（含origin_items补绑定），不是仅结算或浏览器本页累计。list/task_link另给obligation_allocated_amount/expense_allocated_amount，两者不是可相加现金；settlement目的按kind返回allocated_amount/available_amount。候选无资格原因是有限值（建议direction_mismatch/already_claimed/no_available_amount/target_incompatible），不传自由业务正文到日志。`allocated_amount/available_amount`说明现金分配额度，**不能据此暗推一flow可给多任务**；任务认领另验同方向且当前无其他月关联。

GET items的选择目的不同：settlement_target提供 `remaining_obligation_amount`，settlement_source提供 `available_source_amount`；两者并非万能余额。每行都有 `id,version,type,counterparty,content,origin_date,original_amount,project,selectable,unavailable_reason`及适用额度，项目/对象按类型可null。独立新建非现金目标尚无ID时，选择器按获准settlement_kind查询；提交仍验证完整来源/目标。额度、目标兼容、来源相同、单项目约束使用§3.9同一规则；不接受白名单外类型。按全范围条件计数分页，不用旧报表50行当主数据。

**事项和处理明细**

`ItemDetail.item`返回§3.8所有已获准的本体字段、version和系统时间，未适用字段明确null；`amounts`按最终type仅定义有业务意义的金额（如原义务、现金归还、两类冲抵、剩余义务），不得自动假设全部type都有同一减法。`settlements`同样最多20条预览并给 `settlement_count,settlements_has_more`；完整列表GET settlements?item_id或source_item_id。对应现金子表GET flows?item_id，不把同一flow因多条分配重复展示。

`SettlementRow`候选：`id,version,kind,occurred_on,amount,remark,item_id,item_version,item_content,source_item_id,source_item_version,source_item_content,flow_id,flow_version,flow_source_kind,task`。不适用来源/现金/任务为null；返回的是本次快照相关版本，提交更正/撤销时逐项携带，不得只给settlement本身版本。事项本体/流向不符必须冲突，不能将超额“截成剩余额度”。

GET settlements的item_id/source_item_id/flow_id至少给一个；同时给多个按AND明确缩小范围。金额汇总按结算kind分列，不把现金与非现金合成现金余额。date过滤如省略表示该明确父对象的全部历史，仍分页、有界SQL；不能为省事只显示当前月历史。

**任务配置与月度行**

模板行逐一返回§3.6的明确列，包含默认值null和version，不返回全部月份实例。月度行形状为 `row_key,occurrence_id,version,template_id,template_version,month,title,kind,due_on,remind_on,planned_amount,actual_amount,state,marked_unpaid,need_planned_amount,is_over_plan,over_plan_amount,is_overdue,is_due,note,flow_count`。row_key是template_id与YYYY-MM的普通拼接，仅用于UI稳定key，不生成hash或新数据库身份。未落库待办occurrence_id/version为null；template_version仍必须存在。

remind_on以当月due_on减有效快照remind_days得到；核对任务actual_amount=null，不是0元付款；现金任务在明确范围内无有效现金时actual_amount="0.00"。planned_amount是明确月目标；null显示待填，default_amount仅初建时明确预填建议。flow_count是有效现金条数，点击后GET flows?task_occurrence_id分页显示全部，标题“处理明细”不等于新增历史审计系统。首次无记录冲突后，用GET occurrences?month&template_id重读；不能继续向null ID重试写入。

月度summary候选 `task_count,counts_by_state,receipt_actual_amount,payment_actual_amount`，数量按全部匹配任务，不按本页；展示state按§7.2只有pending/partial/completed。模板默认金额、应付目标、已收付三者分别标注。实际金额不因筛选只返回首50条flow而漏算。

**三类账簿精确DTO**

| 行类型 | 输出字段 | 计算/下钻 |
| --- | --- | --- |
| TurnoverRow | row_id,row_kind,ledger_group,personal_variant,occurred_on,item_id,counterparty,project,content,state,original_amount,repayment_amount,reimbursement_received_amount,ticket_offset_amount,non_ticket_offset_amount,real_expense_amount,cash_received_amount,cash_paid_amount,remaining_after_event,flow_id,settlement_id,expense_item_id | row_kind=opening/principal/settlement/expense；row_id=kind+真实ID，非hash；不适用金额null，退款费用列为负净贡献；personal_variant=principal/settlement或null；现金额取本事件份额；opening无现金 |
| TicketRow | id,version,ticket_provider,ticket_provided_on,content,project,provided_amount,used_amount,offset_amount,available_source_amount,receivable_amount,cash_received_amount,state | used含offset；state=unused/partial/used按来源占用算；实际回款只sum明确ticket_source_id公司应收的company_collection，不能推作全部票额到账 |
| PersonalMatrixRow | row_key,bill_label或null,months[12],year_principal_amount | row_key为bill_label ID或明确non_bill；months元素month,principal_amount,item_count；真实已知范围无事件为0，未知起算前不装0；单元下钻GET items按bill_label_id/类型/actual date月，不把bill_month当实际月 |
| 个人三子表 | SettlementRow+bill_label,bill_month,counterparty,project | 分别cash_repayment/ticket_offset/non_ticket_offset，限定personal loan；只按分配金额，actual date筛年 |

Turnover state是该目标义务截至date_to的open/partial/settled，不是任务state。remaining_after_event按item完整事件账序计算再做显示过滤，不能用当前页累计；费用不改变该义务余额，可为null。summary为event_count、principal_amount、opening_adjustment_amount、五列合计、cash_received_amount/cash_paid_amount、remaining_obligation_amount；后者按唯一义务截至date_to计算，并分receivable/payable两项，不能把应收/应付或每行余额直接相加。principal_amount不含opening。

Ticket summary对全部匹配来源汇总provided/used/offset/available/receivable/cash_received，各数独立。提供日筛选决定来源集合，累计使用/回款截至date_to；完整历史下钻可查全期间并注明，不把未来回款混入历史截点。

Personal summary含coverage说明、opening_obligation_amount、opening_adjustment_amount、new_principal_amount、cash_repayment_amount、ticket_offset_amount、non_ticket_offset_amount、remaining_obligation_amount。期初为已知年初未结；年中起算只报告已知覆盖，不能冒充完整年初。个人coverage从settings.personal_opening_date确定；未配置明确unconfigured、派生完整期初null；起算前月份null，覆盖后的无记录月份0，年中起算月标部分覆盖。矩阵下钻使用origin_date_from/to、is_opening=false、type=loan、ledger_group=personal，无卡组has_bill_label=false且不传bill_label_id。矩阵每页最多200个稳定行×12月，不嵌全部item IDs；下钻分页拿ID/version。无账单本金用non_bill组，不挂假银行卡。

ItemDetail.amounts使用四种精确判别类型：loan/company_receivable为original_amount,cash_settled_amount,ticket_offset_amount,non_ticket_offset_amount,remaining_obligation_amount；expense为original_amount,paid_amount,refund_amount,net_expense_amount,available_offset_amount；ticket_source为provided_amount,used_amount,offset_amount,available_source_amount。paid_amount包括origin_flow份额与expense_payment、不重复；refund计一次。不存在万能余额或任意字典。

报表sort白名单：turnover occurred_on/original_amount/repayment_amount；tickets ticket_provided_on/provided_amount/available_source_amount；personal matrix bank_name/label/year_principal_amount，子表occurred_on/amount。末级追加稳定row_id/ID；非法sort400。summary与rows/total同快照，不取当前页合计冒充全结果。

### 8.8 有界读取、排序和已知错误

| 项目 | 技术建议与明确处理 |
| --- | --- |
| 流水/报表期间 | 页面显式传月或年起止；未带范围的普通流水列表400，事项/任务明确父对象下钻可查该父对象全历史并分页。自定义期间建议单次不超过366天；所有年份都可选择，不删旧年数据；多年度同时查询若确需，先确定体验与测量，不无界拉到浏览器 |
| 月任务/提醒窗口 | month、reminder_from/reminder_to、overdue_as_of三选一；跨月提醒先计算受提醒天数影响的模板月份，再在服务端全范围过滤/计数分页。提醒天数0–31、窗口最多62天；逾期范围受真实启用区间限定，集合SQL分页 |
| 列表/预览 | 常规50行、最大200行；详情与删除摘要每类最多20条+总数/has_more；单次复合写最多100条分配为待测建议。账户/分类/任务配置从初版就支持相同分页，不等变慢后才改API |
| 排序 | flows默认occurred_on降序、次created_at降序/id降序，amount排序同样加稳定id；items默认origin_date降序/id降序，支持original_amount；settlements默认occurred_on降序/id降序，支持amount。账户/分类/模板等持久化列表在获准排序后追加id；混合虚拟待办的月任务追加template_id/month。报表只开放最终明确列并追加其确定行身份，所有分页都不能只按可能同值的名称/金额/日期排序 |
| 输入边界 | API日期为合法YYYY-MM-DD、月份为YYYY-MM，与§2.1一致；月份由服务端规范化为当月1日存库，客户端不混传两种格式。时间响应ISO8601带时区。page/order/enum/UUID/array大小/金额逐字段验证；SQL参数化，禁止用户列名拼SQL；不存在的合法ID是404，不混成格式400 |
| SQL/锁等待 | 初期建议现金事务局部statement_timeout=2000ms、lock_timeout=500ms；采用现有受限连接池超时。先查现有配置，若已有更严上限不放宽；仅现金作用域设置并确保归还连接前事务已结束，不修改普通角色/全局PG参数 |
| 查询取消/超时 | 事务回滚、释放连接，返回明确cash_query_timeout或cash_busy（503），UI保留输入并允许手动重试；不把DB超时伪装业务409，不捕获所有异常返回空rows，不自动重复写 |

这些数值是完整设计待批准和实测调整的技术初值，不是新增性能门禁；不可用“达到上限”作为丢数据、拆散一次原子操作或忽略关联的理由。若真实业务超出建议范围，调整有界方案并测量，而不是加隐藏无限查询或假成功。

## 9. 权限、全局历史排除与 OA 边界

### 9.1 同 PostgreSQL 的最少权限

- `cash` schema 归迁移 owner；现金 API 运行角色仅有 cash.* 必要读写，不授予 DDL、超级用户或普通财务/audit/job 权限。
- 普通 API/worker 不获得 cash.* 权限；不把 cash 角色 grant 给普通角色，不使用同一连接动态 `SET ROLE`。
- cash repository 只拿现金连接入口，普通 repository 只拿普通入口；两者复用已维护的池实现。连接总量一起预算，不再额外开一大池。
- 检查 owner/PUBLIC/default privileges、角色继承、视图和 SECURITY DEFINER 旁路；不只检查表名/search_path。
- 现金身份/ACL 在共享安全控制面先判断，cash service 不自行读取普通设置表。现金池不可用只让现金请求明确失败，不回退普通 DSN。
- 同进程和同库仍共享 CPU、磁盘、连接总预算和备份管理权；不能保证被攻陷的整个服务器看不到现金，也不能承诺理论零性能影响。

### 9.2 页面权限只有两个状态

新增现金 page key，普通账号默认不可用；所有现金 Tab 使用同一可用性，不设 reader/editor/admin/删除专属档位。固定 `YNSYLP005` 仍是唯一设置他人页面集合的账号。现金获权用户可以使用现金内部设置，不因此拥有全局 ACL 管理权。

现有 `/api/background-jobs` 的页面集合随 `ASSIGNABLE_PAGE_KEYS` 扩大可能误放行 cash-only 账号：新增 key 时必须保持普通 job 的原 owner 范围，单独测试 cash-only 被拒绝。其他按“所有页面”集合派生的全局注册表同样审阅，不能机械加入现金事实查询。

撤权/退出登录后取消现金请求、清空局部数据；下一次 API 必须按现有 ACL 重新判断。不能保证已下载到有权用户屏幕的数据被远程抹除，设计只控制后续访问和客户端当前受控状态。

### 9.3 全局操作历史与技术日志

已核验的当前通用 HTTP 存在 requested/completed 两处记录。实施采用一个精确 cash route 记录策略，并在两处使用；不把 cash mutation 塞到“只读 POST”名单。不删除普通业务 requested 失败即拒绝写入等保护。

需要逐项验证的出口：

| 出口 | 现金规则 |
| --- | --- |
| requested/completed 与 service audit | 成功、失败、删除、任务、设置均零现金业务事件 |
| DB 触发器/财务修正历史 | cash 表不接普通财务事实触发器；不写 `app.financial_fact_corrections` |
| 全局 job/event/App Health | 不发现金业务任务、摘要、条数或金额；系统审计明确排除，不伪造已审计 |
| HTTP access/performance/error logs | 保留不含业务正文的技术信息；使用 route 模板/粗分类，不记录动态 ID、query 原文、金额、项目、人员、账户、body |
| 前端控制台/错误采集 | 不记录现金 payload、搜索词、表单和旧响应 |
| URL/浏览器持久化 | 不在 URL 查询、localStorage/sessionStorage、全局 store 保存现金正文；必要路径 ID 不能被访问日志原样记录 |
| 普通导出/reset | 不包含、不读取、不删除现金表；未来现金导出需另行明确功能和数据出口 |

005 在现有设置修改页面授权仍属于既有安全控制面审计，保留现有安全措施，不记录现金正文。现金记录上必要创建人/日期不是新增操作历史系统。

### 9.4 OA 实际字段仍须只读核验

2026-09-07 已在 OA UI 看到十个真实阶段名称及列表总数 118；这不等于已验证原始字段路径、全部代码或分页完整性。现有 `fetch_projects()` 固定 `active`、普通本地 completed IDs 均不能作为现金真实阶段。

实施前由开发者核验：项目稳定 ID、编号、名称字段，阶段值与字典关系，空/未知/已删除记录行为，分页/权限范围，权威“已结束”编码。只保存结构和脱敏样例，不把凭据/真实项目全集写入 MD。

只读 all 列表含已结束/未知阶段；selection 只含允许且非结束项目。保存允许集合前查真实字典，未知代码拒绝。历史报表完全基于本地快照，可查已结束或源删除项目；不拿 selection API 给历史筛选供选项。

OA I/O 只在项目列表、阶段设置、新建/改选项目必要校验发生。删除、查询历史、只改无关备注不需要 OA。当前 OA 边界需为“项目主数据按需只读”明确一个窄例外，禁止扩成 HTTP 财务 Mongo 查询或 inline sync。

OA 与 PostgreSQL 无共同事务；服务端复核后源阶段瞬间变化无法消除。以复核时刻判断，不建跨系统事务，也不承诺真正瞬时推送。项目查询失败明确提示，不硬编码十个名称、不回退普通项目快照。

## 10. 测试与性能：实现时执行，不作为本轮结果

### 10.1 必须有的定向用例

| 类别 | 可执行验收场景 |
| --- | --- |
| 业务单元 | 收/付/互转；Decimal 精确金额；期初/跨月；非现金零现金影响；日期/阶段/版本错误；按确认规则算事项金额 |
| 服务事务 | flow/occurrence/settlements 任一位置失败全部回滚；新建/删除/旧重试不复活；锁序一致；关联已有手工保留来源且结算只算一次 |
| API | 严格类型、分页排序、401/403、已删404、冲突409、依赖503；body actor 不生效；成功字段/来源/版本正确，不只断言200 |
| 直接读取 | rows/summary/total 同快照；每个报表/子表/详情/项目选项排除已删；历史余额跨月更新；零 queue/旧 projection 调用 |
| 前端 | 提交禁双击、失败保留草稿、冲突刷新、删除取消/失败/最后一行、旧请求不回填、任务核对无现金、来源/任务分开 |
| E2E | 手工/任务→唯一现金→多账→删除→全账/任务/余额一致；既有现金关联任务；非现金登记→更正/撤销→现金不变 |
| 旧页回归 | 普通银行/成本/往来/发票/导出不变；原 ACL/审计失败保护；cash-only 不能普通 job；普通 reset 不碰现金；cash-special 保留 |

真实 PostgreSQL 测试不可用 mock 冒充：至少两连接并发确认/删除/编辑/结算、唯一冲突、事务回滚、普通角色拒绝 cash、cash 角色拒绝普通业务/audit/job。测试只用受控测试库，不 fallback 生产 DSN，不依赖真实 Excel/OA 或真实业务账号。

特别补充并发次序：新增成功但响应丢失→删除→旧新增重试；物理 DELETE 未提交、旧 INSERT 阻塞唯一键，DELETE 提交后 INSERT 成功但最终已删 ID 检查使全事务回滚；任务确认成功→删除→旧确认重试；删除与新分配同时进行；删除与既有手工认领同时进行；预览删除后另一人修改；不同任务争认同一 flow；两个目标同时消耗同一票据来源；分配后调小金额；编辑已结束项目但不改归属；用户确认项目后允许阶段配置变化。每个场景有一个明确成功结果或冲突，不接受半状态。

聚合用例同时保护“一笔100分配40/60，总现金100”及“两笔各100，总现金200”；每个有金额的主表/子表查询都验证不会因 JOIN 放大或金额去重丢失。

字段细化后必须新增的定向期望（均为实施期用例，本轮未编写测试代码）：

| 编号 | 输入/事件 | 必须断言的结果 | 适用类别 |
| --- | --- | --- | --- |
| TC01 | Money合法零/正/负边界、18位单笔上限；多笔合计超过单笔上限；NaN/Inf/科学计数/JSON数字/布尔/逗号/超小数位 | 按字段符号规则接受或400；不先舍入入库；合法大额SUM精确返回不截断；超范围单笔失败不写半笔 | 单元/API/PG |
| TC02 | 缺必填、未知字段、明确null、空白、0、false、PUT省略字段 | 缺失/非法拒绝；可空字段才允许清空，省略保持，false不被默认true覆盖；空修改不是成功写 | 单元/API |
| TC03 | 展示null、"0.00"、正常金额和非法响应金额 | 前两者分别“—”/“0.00”，正常格式不丢精度，非法响应明确错误不显示假数 | 前端 |
| TC04 | 改传source_kind/actor/project_name_snapshot/余额/系统时间 | 拒绝非白名单字段；可信入口和身份仍是唯一写入来源 | API/安全回归 |
| TC05 | 同flow ID+同金额，但related_items或allocations目标/金额/ID不同 | 409，不把复合不同意图视为成功，不增加/覆盖子记录 | 服务/PG/API |
| TC06 | 原复合创建成功后同请求重放；原目标事项又收到别人另一笔还款 | 返回本次原现金/关联当前结果，不重做分配；目标旧版本不是新写授权 | 服务/PG |
| TC07 | 首次confirm成功丢响应，用同flow ID和expected_version=null重试 | 可证明原结果则200且现金唯一；不先因月实例存在冲突；不同意图409 | 服务/PG/API |
| TC08 | 无现金adjust/check成功丢响应后旧版本再提交 | 409+GET恢复当前状态，现金始终0变化，不默默新建命令/重做动作 | 服务/API/前端 |
| TC09 | 增/改/撤现金分配、改换目标；另一表单带旧flow/source/item版本提交 | 所有受影响既存对象按§5.7一次递增，旧写409；新对象初始1；账户配置版本不当余额版本 | 服务/PG |
| TC10 | 非现金处理建立→撤销→原旧建立请求重试 | 保留来源/目标版本已变化，旧expected拒绝，贡献不复活；现金不变 | 服务/PG |
| TC11 | 源flow已有/无后续结算，被编辑金额或删除 | 1000改800留还款200余600；删假义务留真实200并未分配；不是只有DELETE有来源规则，独立事实不被自动改 | 单元/服务/PG |
| TC12 | 账户7月15日起算100，查询6月、7月、8月；多账户起算不同 | 6月未知非100/0；7月opening=null且从7月15日覆盖；8月正确承接；不因筛选隐藏历史净额 | 单元/查询/API/前端 |
| TC13 | 候选读取后他人分配/认领；旧额度确认；同额不同ID | 资格/额度来自服务端全范围；提交版本/额度冲突，不自动取剩余额、不按金额合并 | 服务/PG/API/前端 |
| TC14 | 模板变更后查看已处理月；模板月目标建议100、当月目标300、实际一笔80 | 快照不改，三个金额不混；核对任务金额null；actual80<planned300故partial；再收220完成，超收不截断 | 单元/服务/API/前端 |
| TC15 | 配置初值[]版本1→显式保存[]→再保存[] | configured false→true→true，版本1→2→2，changed true后false；无项目获准不等于数据库故障 | 服务/API/前端 |
| TC16 | OA缺编号/阶段/未知code、配置变更、嵌套事项选结束项目 | 可空值/不可选原因准确；所有新选项目验证；历史未改归属可读/删；零OA写 | API/OA边界/E2E |
| TC17 | 详情关联数21/201；分页最后一页；删除预览仅20条 | 总数/has_more正确，可逐页看全；一个删除事务处理全部实际专属关联；全部现金视图重读 | PG/API/前端/E2E |
| TC18 | 同日同额/互转/多分配；同名账户/模板/同日虚拟月任务翻页；按项目过滤 | 所有列表有稳定末级身份排序，现金不倍增，逐笔余额仍原账户账序；筛选合计与账户余额不同范围 | 查询/API/前端 |
| TC19 | SQL/锁超时、断开客户端、查询参数超过上限 | 明确失败/取消、事务回滚与连接释放，普通页连接预算不受泄漏影响；零空成功/自动重写 | 服务/PG/旧页回归 |
| TC20 | 普通银行原DTO/formatter使用者与cash-only角色并存 | 不新增普通银行字段/改旧金额展示语义，不跨池/不扩大普通job授权；既有安全保护仍有效 | 旧功能回归 |

TC01的单笔极值按numeric(18,2)生成；TC11/TC12/TC14已有精确期望。所有TC为待实现测试，不得用文档案例替代真实PG执行。

以下补充为本轮复审后必须实现的用例，仍非已运行测试：

| 编号 | 输入/事件 | 明确期望 |
| --- | --- | --- |
| TC21 | 已真实loan迟录同日期现金，origin_items绑定→删除该flow→旧创建重试 | 不重复本金/日期；linked来源解除但真实loan保留；旧flow不能复活，CAS正确 |
| TC22 | payment100建立loan100，同时支付已有expense100；receipt100明确还loan并退该费用 | 每次都仅一flow100；债务/费用各正确一次；总表费用行不重复现金列 |
| TC23 | expense原100、实付50、已退40，再退40或移除原付款 | 可退仅10，越界失败全回滚；明确纠错保留真实receipt；两次合计不超已付 |
| TC24 | 删除错误父义务，真实子expense；删除错误票源，真实company_receivable | item_reference_changes同事务解除/改正引用；金额事实保留，无FK悬空 |
| TC25 | 月目标100已办40，再清null；模板停用/重启跨数月 | 清目标失败且仍partial；不补停用月份、不漏停用前旧月 |
| TC26 | 先改个人起算、未设置OA阶段；个人矩阵起算前后/无卡/分页下钻 | OA configured仍false；未配置不是0；先设日期可再录opening，月份按实际date并排除opening |
| TC27 | 并发改个人起算与新增早期loan；两种额度并发消费 | 统一锁序，无落到新起算之前或超任一口径额度的半状态 |
| TC28 | 已结束/源删除/OA断线项目的既有事项真实结算；同ID重试、任务new_flow、并发改锚点；反例为新选/空分配/假锚点/混项目/夹带新事项 | existing_item正确继承本地项目、现金及结算各一次、无OA请求；重放不因旧锚点版本拒绝已成功结果；新动作版本冲突整笔回滚；selection仍拒绝结束项目，反例无半写，无OA写回 |

TC28还覆盖首次cash为空→识别OA中已结束但真实存在的项目→登记期初未结→R7真实结算：期初阶段flow数量不变，结算时才增加一笔；项目已无任何可信来源明确失败，不生成假项目。重试比较持久化业务结果，不因结果完全相同的请求仅改project_mode就假称可检测并拒绝；不同项目/金额/原关联必须409。锚点因原付款已结清后原请求重试仍可返回原未变结果，不再次结算。

### 10.2 性能目标和测量

- 以 10,000 条合成流水作常用规模、100,000 条作增长实验，事项/任务关联数量随真实业务比例；不是在生产造数据。
- 记录 SQL、连接等待、HTTP、payload、DOM 更新分别耗时；月/年、后页、过滤、事项子表、往期删除后读都测。
- 技术体验目标沿用实施计划：本地正常 GET p95 ≤ 500ms、p99 ≤ 1000ms；PG 写 p95 ≤ 500ms；写后 GET→DOM 目标 p99 ≤ 3000ms。均未实测，不是新增发布 gate。
- 现金与普通页面同窗 1/4 并发，核对旧页延迟/错误/连接等待；不单测现金快就声称旧页无影响。
- OA 单独测有界列表/字典/单项目，初期总超时 2s 为待测建议；不把 OA 慢藏进 SQL 事务，也不以旧值兜底。
- 建议每主要场景至少 100 次有效样本再报分位数，错误和慢样本不删；输出环境、参数类别、规模、并发及查询次数，不保存真实敏感请求。
- 先减少无用列/行、改 SQL/索引、缩短事务、分页再复测；无测量证据不加缓存、物化视图、分区、worker。

具体命令复用[实施计划](cash-module-implementation-plan.md)与现有 verification 入口；不另建现金性能平台或 hash/baseline 系统。最少已删身份表只按主键访问，不能影响普通查询或引出全局清理任务。

## 11. 迁移、旧链清理、发布与临时备份

1. 只在完整批准后创建 cash schema 与已定案表；先核实当前迁移序号，追加新 migration，不改历史已应用 SQL/既有 checksum。
2. 默认不迁移 Excel 历史流水；由用户确认期初与未结事项后手工录入，不悄悄增加导入器。未配置现金账户/期初时显示明确配置状态，不以示例账户开始运行。
3. 最小集成修改仅限 cash 页面注册、授权、审计排除、数据库角色/组装和 OA 窄方法。普通财务核心表和四个现有 worker 不因本功能重构。
4. 旧代码按照调用关系清理：若本次临时 demo/API fake、旧现金 client 或重复式 helper 被真实接线替代，同次移除；未被替代的普通 cash-special、active/completed 项目逻辑、历史 migration 保留。
5. 先用 CodeGraph 定位真实入口/调用，再补字符串路由和全仓动态引用扫描；删除后跑调用者测试。不得“为避免污染”删除仍被普通页使用的安全机制。
6. 正式发布另需授权，沿用 `./scripts/deploy-oa.sh`；不加一套现金专用发布门禁，不把当前文档批准当生产部署许可。
7. 停用/回滚现金页面时保留 cash.* 事实、访问权限和备份覆盖，不 DROP schema/数据库。代码旧版本是否理解 cash 隔离要核对，不能回滚到将现金写入全局历史的版本。
8. 本轮无 DB 操作、无临时备份。将来确需任务专用 dump/恢复副本时登记精确路径/归属，验证成功且不再依赖该恢复点后清理并报告；失败恢复未完成不能先销毁唯一资料。主数据库、既有常规备份/PITR、原 Excel 不删除。

同库备份可能包含现金数据，必须核对原备份访问权限；不能为“保密”漏备份。删除业务记录不承诺抹除已有备份中的历史片段，若用户要求特别保留期限需单独确认，不私自扩大备份销毁范围。

## 12. 设计接受、后端先行与剩余事实

### 12.1 本轮接受与技术合并

用户已接受R1–R7业务规则。本次不是仅添加批准附录：§3已统一具体类型/字段/NULL/可改范围，§4只保留物理正文删除，§5落入来源纠错及最少ID，§6/8明确金额、DTO与R7两种项目上下文，§7统一月目标分次、旧月快照与短月提醒。旧单事项请求、单次/分次双模式、逻辑删除备选、颜色未定、万能事项余额均不作为当前实现路径。

8核心表之外只增加业务已要求的稳定账单别名身份与防已删创建复活的最少ID；它们复用一个repository，不产生新服务/平台。金额RMB两位、正常字段尺寸与资源上限由开发者负责，不把SQL字段名转交用户决定。字段可由普通版本、类型、约束、事务与测试演进，不冻结contract。

### 12.2 仍须验证但不是重复业务问卷

| 项目 | 实施动作 | 当前结论 |
| --- | --- | --- |
| OA原始字段/编码/字典/分页/源权限 | 实施B01只读查真实结构与脱敏样例，B03实现窄方法 | UI标签证据不等于源合同已核验；不能猜字段后宣称OA模块完成 |
| PG部署版本/迁移序号/角色权限/连接预算 | B01核实，B02在明确测试库验证migration与双向拒绝 | 当前未执行DDL或GRANT；同库不是物理隔离 |
| 所有现金函数/接口/金额规则 | B05–B09实际编码、真实PG失败/并发/HTTP链测试 | 本文是实施规格，不是现成实现或测试结果 |
| 原App共享ACL/审计/日志/健康出口 | B01定位、B02/B09回归 | 保留普通保护，现金新page key不能扩大普通job授权 |
| 性能 | B10测服务器/旧页请求；F05测浏览器和DOM | 目标不是实测成绩，不保证理论零影响 |
| 账户/期初/允许阶段/12项任务数值 | 使用设置填写 | 不以真实公司数据作为写代码的前置要求 |

真实源若与计划不同，先修对应窄接口/文档，再实现该模块；其他不依赖的模块可继续。若发现会改变已接受业务范围的冲突，说明具体例子并请求决定，不做fallback。没有新通知/附件/Excel导入/导出/CMS需求。

### 12.3 后端先行的完成边界

唯一执行顺序在[实施计划](cash-module-implementation-plan.md)：B01–B10覆盖非前端，F01–F05覆盖前端。非前端可在一个任务中分步交付；不需为验证后端写临时页面，不要求Figma先导出代码。不保证一天完成，也不把当前询问当实施/新建任务/发布授权。

后端交付应有：cash持久化与受限连接、权限/审计隔离、OA窄只读、全部配置/流水/事项/结算/任务/报表API、真实PG事务并发、HTTP完整业务链与旧功能回归、服务器性能结果、实际接口例子与字段说明。只用mock或单元测试不算后端完成。前端导航、005权限checkbox、表单/抽屉/空错态、前端取消旧请求、页面E2E和DOM性能留F阶段，不提前报完成。

B阶段不得独立生产上线新增cash可分配权限或开放入口：旧客户端保存授权是否丢弃未知新key、session权限列表/空可见页如何表现必须实测；采用本分支本地/测试环境开发，F完成后沿既有发布流程授权上线，不新增兼容别名或功能开关平台。

本轮仅修改设计文档，未写应用/测试代码或migration，未执行数据库、OA写回、备份或发布。当前文档验证记录见实施计划；历史共享MoneyFormat八项通过只是复用依据，不等于现金业务已验证。

### 12.4 R7已确认并合入正文

用户已接受[历史项目结算规则](../product-specs/cash-module-design.md#102-r7-已确认历史项目结算不是自由新增项目)。§2.2定义重试、§5.2定义事务、§8.2定义两种严格DTO上下文、§8.5定义OA边界、TC28定义正反并发用例；不再保留条件稿或待审批分支。

R7复用原flow/items/settlements、manual/monthly_task来源和同一事务，不加表、项目镜像、缓存、worker、状态覆盖或门禁。设计已收口，真实OA字段与PG运行事实仍按B01验证；设计接受不是本轮代码、数据库或发布操作。
