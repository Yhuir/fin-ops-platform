# 成本统计

入口：`/cost-statistics`。

根据银行用途、OA 费用单元、正式来源和人工决定生成唯一成本事件集合，提供项目、费用、账户、时间和标签视角。

## 边界与 I/O

输入：view/filter/cursor、成本范围配置，以及逐 OA 单元金额、来源、oa_amount_locks、oa_cost_tag_overrides、version/fingerprint。输出：聚合、下钻、来源详情、待分配/人工记录和导出。

## 当前业务约定

- 银行视角的原始流水详情复用银行来源详情 API 与公共抽屉；成本分配明细属于成本业务事实，保持独立，不能混入原始单据字段。

- 五个明细视角共用 `GET /api/cost-statistics/explorer`：`identity_names` 为 JSON 字符串数组（最多 200 个名称，每项最多 200 字符，空字符串表示未填写），项目成本匹配 `oa_applicant`，银行流水匹配 `counterparty_name`；`sort_order` 为 `asc`/`desc`，默认倒序。多姓名为 OR，与日期、搜索、下钻条件为 AND。同名记录一起匹配。
- `identity_options` 来自当前日期、搜索及下钻范围、姓名筛选之前的完整候选集合。姓名条件只改变明细和 `row_count`，不改变范围汇总和左栏分类金额；排序和姓名条件绑定分页游标，变更后回到第一页。时间使用现有 `occurred_at`，缺失时间始终最后，同时间按稳定行身份排序。
- 五个视角的姓名/排序状态隔离；变更分类、日期或搜索清空该范围的姓名筛选并保留当前视角排序。筛选菜单允许多选、搜索、清空，点击应用才查询。导出中心使用自己的明确筛选条件，不继承右侧明细姓名条件。
- 按银行账户的列表项分两行展示银行名称和尾号，原始账户键保持不变；银行流水按标签保留主/子标签列，主标签 chip 仅显示子标签数，子标签仍显示流水数量。
- Repository 负责同快照批量取事实，Policy 是无数据库/网络 I/O 的纯计算，query service 组装 DTO，人工 service 通过 repository 事务保存。
- 银行外部往来本金按结构化 turnover_role 排除；独立利息用途有唯一来源且金额闭合时自动计成本，金额或来源歧义保留待分配。
- 自动分配在正式关联范围内使用明确来源引用、正式历史约束、唯一金额对应，以及共用付款证据函数认定的双方唯一匹配（金额、收款方、日期/付款阶段，账户/币种/方向不得冲突）。不能把展示同行、顺序、最近日期或总额相等当作来源证据；完整覆盖当前所有 OA 和支出的双方唯一付款证据优先于历史合并分组；不完整证据不能解除历史范围，明确来源引用冲突仍阻止自动分配，已有人工决定保持原样。
- 先确定付款来源，再应用 OA 审批准入。进行中 OA 不计项目成本；其来源金额逐笔有据且所有范围内付款均闭合时，仅等待审批，不进入待分配列表/数量。独立已完成部分立即计成本。银行按标签/时间视角仍展示原始收支。
- 1:1、1:多、多:1及可拆成确定来源组件的多:多自动计算；无法确定来源、金额差异、缺少必要来源资料或 stale 人工决定仍进入人工处理。不会为同额歧义强行排列匹配，也不自动按比例分摊。
- OA 同步完成后，下次 canonical 查询计入已具备来源的金额；状态退回则撤出该部分，关联撤销后不再计该关系成本。不生成 automatic 人工记录，不覆盖既有 manual 金额/来源。
- 原有详情合同保持：`unallocated_amount` 表示尚未计入成本/非成本的金额，可包含等待审批部分；是否需要人工处理以 `pending_reasons` 为准。仅 `oa_in_progress` 不进入待分配，真正未确定来源仍保留 `source_required`/`amount_required`。
- 待分配抽屉每次打开全部折叠，点击项目才请求详情。关闭再打开不恢复展开；同次访问刷新只保留仍存在且用户未折叠的项目。异步返回不能自动展开第一项。
- 无决定或 automatic 按当前事实计算，manual 优先；stale manual 进入复核，不静默转自动。自动完成不要求保存人工记录。
- OA 原额锁定按单元控制；解锁只改变分配金额，不修改 OA。来源容量、退款、非成本和范围外已确认金额一并校验。
- 人工成本标签只属于成本事件，不能改银行标签或扩大来源准入；保存保留范围外有效决定，CAS、版本和审计同事务。
- 银行用途改变由银行 owner 调用成本撤销端口，保留审计和连续版本；纯排序变化不撤销决定。
- 银行视角不加载无关人工分配；OA payload 只读取计算所需字段，分页/导出共用业务策略。

## 依赖方向

[银行明细](../bank-details/README.md)、[正式关联关系](../workbench-relations/README.md)、[OA 集成](../oa-integration/README.md)、[设置](../settings/README.md)、[外部往来款](../turnover-ledger/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [web/src/pages/CostStatisticsPage.tsx](../../../web/src/pages/CostStatisticsPage.tsx)
- [backend/src/fin_ops_platform/app/routes_cost_statistics.py](../../../backend/src/fin_ops_platform/app/routes_cost_statistics.py)
- [tests/test_bank_split_cost_migration_service.py](../../../tests/test_bank_split_cost_migration_service.py)
- [tests/test_bank_split_relations_postgres.py](../../../tests/test_bank_split_relations_postgres.py)
- [tests/test_bank_split_consumers_postgres.py](../../../tests/test_bank_split_consumers_postgres.py)
- [tests/test_cost_statistics_policy.py](../../../tests/test_cost_statistics_policy.py)
- [tests/test_cost_statistics_canonical_repository.py](../../../tests/test_cost_statistics_canonical_repository.py)
- [tests/test_cost_statistics_api.py](../../../tests/test_cost_statistics_api.py)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。
