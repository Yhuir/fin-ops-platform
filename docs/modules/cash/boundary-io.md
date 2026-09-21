# 现金账边界与 I/O

## 普通历史范围默认全部（2026-09-21）

`GET /flows`、周转 `view=events` 和有票支付 `view=period` 接受 `time_scope=all`，与任何 `date_from/date_to` 互斥。服务按上海业务日注入今天作为截止，无起点；未提供 all 时，原成对日期及最多 366 天校验保留。独立普通列表缺少两种时间表达仍为 400；明确事项/任务父对象的无日期历史合同不变。纠错候选复用 flows 的 all，任务关联仍传任务月身份；个人年、未结/待回款截止日及所有写命令日期不变。

现金 rows/count/summary 继续来自同一只读快照并由 SQL 分页。all 的 `flows.summary.period={date_from:null,date_to:上海今天}`；账户余额按各账户真实 opening_date 至今天的完整账序，关键词/项目过滤只影响 filtered_totals，不改变余额期间，空筛选结果也保留账户余额。未起算覆盖仍为未知；不新增报表字段、表、worker、缓存或普通财务 I/O。

CashFlows section wrapper 与 CashBooks lazy initializer 在首请求前清普通日期，仅实际改变日期时清页码，保留非日期筛选/排序/视图；CashBooks 同时清隐藏的 events/period 条件。section 内 Tab、本页刷新/保存/抽屉关闭保留本次日期；切走 section 再进入恢复全部。复用 CashFlowTable 不在每次挂载时清父对象条件；不增加全局 store、sessionStorage、URL 日期或 CashContent key/effect 重置。全部/自定义互斥显示；历史项目候选不接受新 scope，all 仍调用既有 project-options 并传 `date_to=上海今天`，父对象候选继续携带父 ID。

## 待实施增量：Excel迁移闭环

本轮闭环实现按技术§14执行，实际验证和发布见实施§16。cash内部新增三列（专账人员、事项分类、无来源调整分类），新增未结/待回款读取视图及个人来源项目/分类筛选；不新建服务/表/账号/worker或缓存，不改普通金融DTO/全局历史/OA写边界。UI显式组装既有命令，repository只读写cash；个人跨项目只限明确同人归属的非现金，现金项目约束保留。配置共享读锁先于稳定主键行锁，不把现金写串行化为全局排他锁；修改来源会验证其费用引用及后续冲抵并整体回滚。历史已结束项目未处理票据/费用开账未获窄方案前不放宽资格。

## 本轮边界（统一UI）

以下统一边界已实现，最新验证及发布状态见[实施§14](../../dev/cash-module-implementation-plan.md#14-统一现金ui实际执行与验证2026-09-08)。后文“API不变”描述上一轮修复，本轮新增读取参数见[技术§13](../../dev/cash-module-technical-design.md#13-统一ui与多选读取实施细节)。

- 布局/控件：CashPage/CashUi/cash.css组合单表/分组/配置；CashFilters.tsx只接类型化值/选项/状态/callbacks，输出apply/clear/sort/search/page/open，不取数、不算账、不识别OA资格。Checkbox用slot=null脱离表格行选择上下文；应用回调可返回校验信息，不把无效草稿提交为已应用条件。
- 业务视图：四子页及关联抽屉拥有列能力、草稿/已应用条件/rows，cash内恢复条件但不持久化；候选owner负责历史/录入范围，不能把页面业务下沉到共享FinanceTable/AppDrawer。
- 共享表格：仅给FinanceTable补可选sortDescriptor/onSortChange并转发到HeroUI Table.Content，输出列/方向，不请求API、不排序业务数据；未传这两个props的既有页面行为不变，纳入公共表格回归。
- 读I/O：新增明确JSON数组查询，保留合法单值、禁止同一字段单复数同传及重复key；SQL集合过滤在分页前，保持摘要/完整账户账序差异。items的project_ids只为保留个人矩阵月格下钻范围；OA只增加阶段列表过滤，不改写入或资格保存合同；GET无写副作用。
- CSS/Portal：现金局部样式类显式传入浮层，撤权/退页卸载；不修改普通页面默认主题、全局store、日志或请求链。
- 旧代码：内联历史项目/费用/账单面板、更多筛选details、重复排序、内联余额/说明和手写Tabs随调用方迁移删除；实际录入条件、公开单值API、cash-special及安全确认不误删。清单见实施§13.4。
- 数据库10表、账号、service/repository责任、写事务、资金公式、普通财务隔离不变，无新worker/cache/迁移/备份。测试七类及浏览器全展开态、规模/混合负载按实施§13，不复用历史空库结果冒称通过。

## 责任与依赖方向

`Application` 认证/页面授权 → `CashApiRoutes` 解析和 HTTP → cash service 命令/查询 → cash repository SQL → 同库 `cash.*`。

`CashRuntime`在现金页面授权后惰性组装有界PostgreSQL连接；复用`PostgresSettings.from_env()`，与普通App使用同一数据库、同一登录账号，不另配cash DSN或密钥文件。池最大2、等待8、获取超时2秒、SQL超时5秒，既有更严限制不放宽；小池仅约束资源，不提供权限隔离。配置错误或数据库不可用明确503，不创建替代数据。0167仅给既有`fin_ops_app_runtime`授予现金10表DML；cash repository只读写cash.*，普通repository不得读取cash。此为应用模块隔离，不是数据库账号隔离；实际部署须核对全机连接预算。

请求级 `CashOaProjectService` 接收可信 session token 对应的字典读取函数、现金阶段设置读取函数及共享有界 Mongo client。只 GET `XMJD` 字典，Mongo 只投影 form 17 的项目 ID/名称/编号/阶段；不写 OA，不查财务表单，不把 token 留在共享服务中。OA 未配置仅影响依赖它的项目操作；本地历史事项结算不调用 OA。

## 输入

- `/api/cash/*`：必须先认证并拥有页面 `cash`；005 管理员可用，普通账号只有可用/不可用。只有 005 能在既有平台设置修改页面 ACL。
- 金额用两位十进制字符串，日期 ISO、月份 YYYY-MM、ID UUID；未知/重复字段、重复 query key、非法类型和状态明确失败。完整字段与版本见[技术设计](../../dev/cash-module-technical-design.md)。
- 手工创建与任务确认共用同一现金命令事务；核对/未办不造现金。新建真实项目、自由改项目取 OA 当前资格；既有事项结算沿用本地项目。

前端已实现（2026-09-07本次修复）：左侧四子页面统一cash权限，单`/cash`入口以section=flows/accounts/tasks/settings承接导航；非法、重复section或多余参数明确报错，裸路径规范到accounts。shell只持非敏感标识，不读现金数据、不显示金额或任务数；正文局部视图拥有业务请求和0/3/2/4菜单。OA checkbox只保存现金project-selection配置，全部项目与新增候选分开，取消状态不隐藏历史。无新权限层级。

CashFlows只组合既有表格/录入，不复制业务；CashBooks已移除通用flows Tab/新增但保留上下文实际收付。CashFlowTable的itemId/taskOccurrenceId嵌入明细保留；CashConfigurationSelect仅负责启用项录入，CashConfigurationFilter负责全部历史候选。单值API/同库同账号/唯一cash权限/无全局历史边界不变，CSS仅现金及现金Portal；新增GET集合参数见技术§13，执行证据见实施§14。

实施细节复审：CashConfigurationSelect已删除无消费者的mode/filter分支，不保留并行旧筛选路径；父对象嵌入流水默认全历史分页，独立流水必须带显式 all 或期间。已应用筛选/排序/页码仅存于CashProvider可卸载子树，切回重新GET；撤权/退页条件和rows均清空，不把条件留在Provider之外。删除末页用查询返回的total调整页码，不重复删除命令；多表页只设一个内容滚动区。上述仍是cash内的UI/查询责任，不改变Shell合同。

前端请求owner为features/cash/api.ts：复用底层apiFetch，现金路径单地址严格JSON/HTTP，15秒超时，不调用自动换地址重发的apiRequestJson；不从普通业务client查分类/项目/金额。hooks.tsx只在CashProvider内维护请求取消和局部revision，写成功重新GET，401/403卸载敏感子树；无storage、全局事件或全局overlay写入。复用FinanceTable/AppDrawer纯UI，不复用useFinanceTableSession；关闭的现金抽屉条件卸载，Portal样式仅.cash-drawer范围。

已补充TurnoverRow.category、remark、ticket_collection_state，来源/空值/截至日期口径见技术设计§8.7；分类/备注只JOIN当前页，回款复用集合聚合，无N+1。个人橘/绿筛选personal_variant在SQL分页前执行。/items新增list-only origin_flow_id/related_obligation_id/ticket_source_id关系筛选，父对象不存在404；CashFlowCorrections有界读取关系，只收集明确动作和CAS版本，随一次最终保存/删除提交。OccurrenceRow的instructions/default_account_id/default_category_id严格来自当月快照，未来模板变更不覆盖历史。不改变普通银行DTO。

## 输出和禁止出口

- 现金 DTO 只返回现金页；现金事实包括 flows/items/settlements、任务及配置，共 10 表。报表直接读同一事实，不复制报表流水。
- 写入以一个事务完成，删除正文及关联贡献同步生效；保留其他真实收付。已删 ID 表只含类型与 UUID，不含业务正文。
- cash GET 用短一致只读快照、SQL 聚合/分页；GET 不生成任务实例、不入 queue、不读普通财务。
- cash 全部响应 `Cache-Control: no-store`；全局 requested/completed 审计、App Health 页面事实检查、按接口页面统计都排除现金。HTTP 技术日志只保留通用 `/api/cash`、状态和耗时，不保留 ID/query/业务异常正文。
- Gunicorn 通过 `app/cash_access_logger.py` 同样脱敏现金请求路径，普通日志保持原行为。Nginx/外部日志不属于 Python logger 的控制范围，部署须验证代理层配置；未完成时不得宣称完整生产隐私链已验收。
- 不向 `app.*`、`audit.*`、`job.*` 写入现金操作。平台 ACL 的既有安全审计保留；它不包含现金流水内容。
- 普通 reset、导出、银行余额、成本、往来、发票、worker、read model 不读写 cash。共享登录/数据库原语不是共享财务事实。

## 文件与旧链路

现金代码入口见[README](README.md)，共享改动限 `server.py/http_adapter.py/route_access_policy.py/access_control_service.py` 的组装、精确策略与日志；不更改普通现金收入/cash-special 的业务。它们不是本模块旧版，禁止误删。现金源不用旧 OA active/completed adapter，不恢复已退役 read model 或兼容池。

2026-09-07按用户同账号要求移除尚未上线的`cash_runtime_identity.py`、独立账号provision工具、对应角色专项测试及cash env示例/加载项；保留并迁移真实CashRuntime录入/读取/删除测试为同账号链路，旧方案只保留在Git和明确标注的历史执行记录，不进入运行时。

## 验证与发布

见[测试矩阵](tests.md)、[执行证据](../../dev/cash-module-implementation-plan.md)和[部署说明](../../operations/cash-module-deployment.md)。后端部署不等于页面交付。代码回退保留 cash 数据与权限；禁止 DROP 主数据库或现金业务表。生产只读验证不能代替测试库的写入/并发/回滚验证。

## 2026-09-10 新增流水入口

CashFlows 管理 section 入口日期初始化及抽屉开关；CashFlowEditor 在普通新增内管理 receipt/payment/transfer 单选与草稿，任务/事项固定方向，已有流水保留方向选择及更正流程。类型切换保留日期、金额、用途、人员、备注、项目和各角色账户，清除分类；有相关事项先显式确认再清除。确认期间不能保存，不复制草稿或猜账户。转账使用转出/转入账户标签，不提交分类与关联事项。删除旧新增 Dropdown 和普通新增方向 Select，列表方向筛选不变。现金 DTO、HTTP、service/repository、权限及读写事实边界不变，未新增公共组件、依赖或迁移。样式限定 .cash-drawer。

## 右侧抽屉交互（2026-09-15）

本模块复用的右侧抽屉遵循[统一关闭行为](../../dev/right-drawer-dismissal.md)：外部点击/Esc 不关闭，X 继续执行已有关闭保护。业务 owner 持有保存/确认完成状态，公共 AppDrawer 仅展示 `completion`；不改变本模块后端 API、权限、事实写入及查询 I/O。旧的重复退出按钮和成功自动关闭路径已移除，内部编辑取消仍按局部职责处理。
