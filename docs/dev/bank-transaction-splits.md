# 流水拆分 I/O 与验证

业务事实见 [流水拆分](../product-specs/bank-transaction-splits.md)。本次不使用 GSD。

## API

- GET /api/bank-transactions/{parent-or-child-id}/splits：解析原流水，返回 transaction_id、canonical_transaction_id、amount、written_off_amount、direction、version、category_code、parts、tag_definitions、can_edit。
- PUT 同一路径：输入 version、parts[{id?,category_code,category_label_path,amount}]；金额为十进制字符串；空 parts 撤销时提供 category_code 与 category_label_path。actor 来自登录身份。成功返回持久化完整对象、changed、affected_months；旧版本 409、不合法合计/金额/标签 400、流水不存在 404、无认证 401、无页面授权 403。
- POST /api/bank-transactions/splits/query：输入 transaction_ids[]，输出 rows[] 与输入顺序一一对应。两个子项属于同一父项时仍按请求数返回，避免位置错绑。固定次数 SQL，无逐行 load。
- tag_definitions 是显示合同，含 code、label、path、primary_label、sub_label、status 与配置语义，不暴露自动分类规则全文。子项与配置分开持久化，标签更新不复制成银行原始事实。
- 平级系统标签在字典中允许 `path=[]`，拆分显示投影使用该标签自身的 `label` 作为唯一层级；有输出层级的标签使用配置层级。两种现有标签形态均纳入单元与真实 PostgreSQL 测试，不修改分类语义。

## 分类实例合同（0180）

`category_payload` 保存每个子项人工选择的完整分类实例：category_label、category_primary_label、category_sub_label、category_third_label、category_label_path、turnover_role、turnover_action_type、turnover_family。GET 的 parts 以及未拆分根对象均返回这些字段，category_path 为完整 category_label_path 的展示别名；根对象始终返回 turnover_third_label_options，未分类 path 为 []。外部往来使用现有往来类型选项，客户端只提交完整路径，family/action 由分类 owner 从配置与第三层规范派生，禁止按银行名称或父流水猜测。

外部往来前两层必须与所选 definition 相同，第三层必须在现有选项内；普通标签路径必须与 definition 相同。矛盾的 family/action/层级信息显式返回 400。仅修改第三层也增加拆分版本并审计，保留子 UUID；业务关联与成本是否变化由其 owner 根据有效金额/成员决定。

0180 将快照投影为 units.split_category_payload，公共 effective category query 和各抽屉读取同一事实。旧 code-only 子项缺失的实例归属不能自动推断；只能以已核实原始分类证据执行一次显式保存，审计保留前后值。新增或编辑子项必须完整保存实例，不能读取时回退父分类。往来 extras 迁移以完整 before 实例重建旧状态。

银行明细关键词可匹配父流水原金额以及子项金额；分类筛选匹配子项，分页和汇总仍按原流水计一次。实例第三层参与筛选和标签展示，余额与原金融事实不变。

## 模块与事务

route 仅 HTTP/session 映射；BankTransactionSplitService 校验金额及版本并编排一次事务；PostgresBankTransactionSplitRepository 只拥有银行拆分表与审计。BankTransactionSplitRelationService 调用关系、成本、批次与往来 owner 的事务端口，失败整体回滚；提交后只发布既有关系内存 delta。

锁先取关联成员有序 advisory locks，再锁银行父行并重读金额，防 split 与 relation 写互锁；版本 CAS 防覆盖。子项属于多个关系时撤销拆分需先撤回相关关系，不合并不同业务意图。历史记录保留原证据；恢复时只允许明确完整身份组投影到当前子项，禁止恢复已删除成员。

BankTransactionUnit 是服务层只读用途 DTO，继承银行字段用于现有行组装，但不送入导入写口。原始银行详情独立使用 parent_transaction，金额统计使用 unit.amount。标签由配置 role/code 决定；凭证核对通过 `bank_unit_comparison_rows` 适配共享用途选择规则，允许本金专属 OA 正确核对，也防止利息 OA 累加本金。

## 旧链路清理

- 用途 SQL 由 app.bank_transactions 切到 app.bank_transaction_units；银行余额、导入去重、主身份审计保留原表。
- 成本不再依靠外部往来本金填写“不计成本”来伪装用途；既有外部决策由迁移工具撤销。
- 父流水已拆分时旧整笔标签写口明确拒绝，不默默覆盖子项。
- 共享 TwoColumnTagPicker 替换成本专有重复选择器，各银行抽屉复用同一拆分组件。
- 往来旧内存分类中的固定类别列表/手工回退改用配置语义及 canonical query owner。

## 测试矩阵

| 类别 | 必须验证 |
|---|---|
| 核心单元 | 精确分币、无效/重复/外来身份、同标签多项、空项撤销、语义角色、无本金重复计费 |
| 服务/持久化 | 原事实不变、完整事务回滚、并发版本冲突、关系/成本/批次/往来审计、无重复副作用 |
| API | 单笔/批量形状、权限、会话actor、错误状态、版本冲突、完整回读 |
| 查询/缓存/后台 | canonical 列表与汇总一致、标签筛选、父行计数、关联事件、批量读取；无新增read-model/worker |
| 前端 | 双栏选择、加删改、合计、保存错误、关闭重开、多笔草稿保护、所有详情入口 |
| 端到端 | PostgreSQL保存→用途投影→往来/成本/待票，真实浏览器提交/回读，发布后生产回读 |
| 旧回归 | 未拆分、导入/撤回、余额、批次/撤回历史、OA/发票、权限、过滤分页与导出 |

## 发布与数据处理

先提交并推送 remote main，唯一发布入口 ./scripts/deploy-oa.sh。0178/0179 引入拆分存储/用途视图；发布后若已写拆分事实，旧代码不能解释用途，不允许回到旧读取链路。

撤销历史外部成本先运行 `python3 -m fin_ops_platform.tools.revoke_external_turnover_cost_allocations` 预览，再以 `--apply --operator <会话操作人>` 同一事务执行，随后再次预览应为零。生产通过 `sudo -n /usr/local/sbin/finops-deploy-control external-turnover-cost-revoke <release> [--apply --operator <actor>]` 加载既有运行环境；执行后使用既有 restart 命令清除进程中的关系快照。工具只撤销被识别的成本决策与其确认状态，不删除银行/OA/发票。审计保存撤销前数据用于明确恢复。

如发布产生临时数据库备份，验证成功后只移除本次 exact backup 文件；不得删除主数据库。测试仅使用名字明确标识 test 的隔离数据库，任务结束清理本次测试库。

性能目标沿用现有合同：读 p95≤1000ms、p99≤2000ms，写到可见 p99≤3000ms。记录样本数与环境；单次生产样本或 no-op 写不能证明完整写入 p99。完成证据在此文后续发布记录追加。

## 性能探针

`finops-deploy-control bank-transaction-split-smoke <release>` 在单个回滚事务内创建自有测试流水，按当前有效标签运行 100 次真实拆分校验、持久化、关系 owner、审计及用途投影读取，并确认父流水/审计均未残留。它不修改真实业务流水，测量不包含 HTTP、提交及已有关系场景，不能替代 HTTP 写到可见 SLO。HTTP 读取使用正式 release gate；隔离 PostgreSQL 的完整提交后回读另行记录。

## 本地验证记录（2026-09-24）

- 后端 pytest 全量收集 4,990 项，首轮 4,903 passed / 32 failed / 55 skipped。失败涵盖独立普通成本被本金专属 OA 干扰的实际回归及旧 SQL/启动/标签/发票来源测试合同；逐项修正后，全部失败所在的 9 个测试文件统一复验 284 passed。未跳过或放宽失败断言。旧发票来源期望按已有 2026-09-20 OA 来源优先合同更新，未改发票生产逻辑。
- 成本所有测试在真实 PostgreSQL 下 184 passed，含独立普通费用保留及共享 OA 不误删。
- 现金独立 PostgreSQL 补测 127 passed；全量默认未提供现金专用 DSN 的跳过由此补充覆盖。
- 前端 113 文件 / 1,509 测试通过，拆分浏览器流程 1 passed；生产构建、Ruff、docs、diff check 均通过。
- 本地完整事务提交并回读 100 次：p50 18.97 ms、p95 22.32 ms、p99 26.83 ms；批量读 100 次 p99 17.07 ms。该数据不含网络，也不代表已有复杂关联的生产 HTTP 写入分位数。
- 原银行表的余额、身份与金融金额不变，子项保存、并发冲突、失败回滚、往来/成本/待票/OA、批次及导入撤销均有针对性验证。生产发布记录由既有 release gate 持久化，发布后另跑统一抽屉、拆分读 API、金额错误拒绝与事务回滚性能探针。

## 2026-09-24 闭环修复发布合同

0180 持久化完整分类实例。成本删除拆分后一律人工确认的旧门禁；明确唯一等额关系自动入账，有效人工决策不覆盖。核对范围合同见产品说明；纯函数和 SQL CTE 共享测试保证关联台分区、OA、进项与销项一致，禁止页面分别减本金或忽略全部外部往来。

发布后运行 `python3 -m fin_ops_platform.tools.retire_bank_split_confirmation_flags` 只读预览，再带 `--apply --operator <actor>` 原子移除已退役标记。工具不改变关系版本/成员，不清空有效成本决定，重复运行返回零。既有 code-only 本金按已核实的原三层分类，经正式拆分 PUT 保留子项 ID 修正，不进行 SQL 人工猜测回填。0180 为新增字段与用途视图投影，无需全库备份，不删除主数据库。

验证覆盖七类：纯用途核对与金额规则、真实 PostgreSQL 分类/成本/往来及回滚、API及权限合同、canonical 查询/分页/summary/full一致、按钮/抽屉与错误交互、跨模块及浏览器流程、未拆分和旧人工决策回归。没有新增缓存或后台任务，验证现有事件的事务边界即可。

### 本次闭环修复验证（2026-09-24）

- 后端全量 `FIN_OPS_TEST_DATABASE_URL=<isolated-test-db> PYTHONPATH=backend/src python3 -m pytest tests -q`：4960 passed、7 failed、55 skipped。7项为分类测试 SQL 漏新增 action/family 字段、migration 计数与现金专用数据库命名要求；更新测试合同并使用专库后，失败所在文件 21 passed。未放宽断言或隐藏失败。
- 最终合并链路复验（拆分、成本、待票、进项、OA、销项、关联台查询及撤回）：552 passed。新增真实 PostgreSQL 同一数电发票不同明细各属独立关系的合法场景；SQL、页面组装及候选/写入 preview 一致。主列表是否需票仍由标签配置决定。
- 现金专用库另验 103 passed；发布脚本、运行配置与核心规则 68 passed。未修改现金业务实现。
- `bash scripts/verify.sh frontend`：114 文件、1513 tests passed；TypeScript 与 Vite 构建通过。浏览器拆分新增/保存/重开/保存失败恢复流程 1 passed。`lint`、`docs` 和 `git diff --check` 通过。
- 55个全量跳过包含需要独立现金 DSN 的测试（已专库补测）及已有显式可选环境测试；未为此次修复新增 skip。生产性能与业务验证在发布后进行，不能以本地单元测试或 no-op 保存替代生产结论。

## 2026-09-24 银行原始金额与用途金额展示合同

OA 待付款、进项发票使用、销项收款的银行聚合对象，以及待找发票的 `bank_transactions`，均输出 `original_amount`（按父流水身份去重的原始金额合计）、`original_transaction_count`（父流水数）、`bank_split_parts`（涉及父流水的完整拆分明细，按父去重）。单笔 summary 输出 `parent_row_id` 与 `original_amount`；待找发票 primary 也输出二者。没有流水时金额为空字符串、父流水数为 0。

原 `amount`、`paidTotal`、`receivedTotal`、`payment_summary` 继续表达用途/单据核对金额，不用于银行总额展示。银行金额筛选、排序与原始总额一致，关键词同时可命中原始金额和用途金额；关联详情复用父流水去重。标签组件只做展示，不参与分类与金额计算。待找发票删除按 definition 自行拼拆分标签的 SQL，改用银行拆分 owner 的 `decorate_parts`，优先消费已持久化完整分类实例，包括第三层。

查询仍为现有 canonical 只读快照、服务端分页和批量 hydrate。没有新增页面 read model、worker、数据库 migration、事实写入、缓存或逐行查询。列表悬浮不发请求；现有编辑命令成功后页面重新 GET。

进项导出“流水金额”使用原始合计，增加“关联金额”和“流水拆分”；销项“收款金额”使用原始合计，增加“关联收款金额”和“流水拆分”。待找发票导出修正已退役 `bank_transaction` 单数入口，读取 canonical `bank_transactions.primary`，借贷列保留主原流水金额，并增加“流水金额合计”和“流水拆分”；已付合计仍为业务金额。OA 导出仅导出 OA 事实，保持不变。

验证入口：`test_bank_split_document_scope_postgres.py`、`test_bank_split_consumers_postgres.py`，验证本息拆分的展示与业务金额隔离、同父去重、多父完整标签、金额筛选/子项搜索、持久化第三层和导出；并回归四个消费页面的 query/API/service/export 测试。

关联台的完整父拆分信息由现有 `workbench_category_projection_rows` 一次 SQL 提供，原单行/full/summary hydration 均经过此边界。选中用途限定父集合后，集合聚合全部兄弟子项，再调用 owner 的装配方法；不额外查询、不复制关联成员，也不改变选择金额。真实 PostgreSQL 测试将父流水两个子项放入不同 case，验证展示完整但当前 case 仍只有自己的 child ID。
