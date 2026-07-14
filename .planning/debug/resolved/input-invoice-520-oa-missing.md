---
status: resolved
trigger: "云南立孚科技有限公司 520 元进项发票及对应已完成 OA 在进项发票使用情况可见，但关联台找不到；完成根因修复、发布与生产数据验证"
created: 2026-07-14
updated: 2026-07-14
resolved: 2026-07-14
---

> 历史诊断，已被 Phase 21 取代：本记录只修复“正式关系被旧 `case:decision:*` 列表过滤”的早期问题，并按当时口径把 OA+发票关系显示在 `open`。当前产品合同要求所有 active 正式关系显示为 `paired`，其余 canonical facts 各自显示为 `unpaired`；2026-07-14 对现网的只读复核仍看到该 520 关系为未配对，因此下文的旧发布记录不是 Phase 21 的生产闭环证据。

# Symptoms

- expected: 统一事实源存在的 520 元发票和已完成 OA 应能进入关联台候选或关系展示。
- actual: 进项发票使用情况显示发票 `26532000000716859331`、供应商 `云南立孚科技有限公司`、金额 `520.00`，并显示一条杨丽萍的 520 元 OA 摘要；关联台查不到相应发票和 OA。
- errors: 页面无显式报错。
- timeline: 2026-07-14 发现；是否曾正常显示未知。
- reproduction: 在进项发票使用情况查询云南立孚科技有限公司并打开 OA 详情，再到关联台查找同金额发票及 OA。

# Current Focus

- hypothesis: confirmed and fixed。关联台 `open` 分组列表和 all-scope 旧防御逻辑把已经正式化为 `manual_confirmed` 的 decision-origin 关系误判为内部 `automatic_decision` 并过滤。
- test: passed。month/all groups list、group detail、真正 automatic decision 负向语义、all-scope 聚合、Redis page-cache invalidation、本地全量后端/前端/浏览器回归和生产只读页面审计均已验证。
- expecting: achieved。未修改 canonical relation、active generation、worker 或下游 relation I/O；现有 fresh active generation 直接恢复可见性，内部自动建议仍不泄漏。
- next_action: none；生产 release 已激活，目标数据与页面审计稳定通过。

# Evidence

- 生产只读查询 `/api/input-invoice-usage/rows?keyword=26532000000716859331` 返回唯一发票 `inv_imported_0369`，金额 `520.00`，OA `oa-pay-2169`，`relationStatus=linked`、`relationSource=manual`、`relationCaseId=decision:2026-05:oa_invoice_exact_amount:oa-pay-2169:inv_imported_0369`；read model 为 fresh。
- 发票详情 API 返回发票号 `26532000000716859331`、销方 `云南立孚科技有限公司`、价税合计 `520.00`，并保留两条手工导入来源记录。
- OA 详情 API 返回 `oa-pay-2169`、OA 单号/流程请求 ID `2169`、`workflow_status=completed`、详情字段 `流程状态=已完成`、完成时间 `2026-05-20T03:52:12.377000`。页面公共字段 `status=open` 是关联台展示分区状态，不是 OA 工作流状态。
- 发票和 OA 的关系详情均返回 active/linked；关系中没有银行流水，因此按关联台状态机应留在 `open` 区，而不是 `paired` 区。
- 关联台页面审计与进项发票使用情况页面审计均为 PASS/fresh，队列已排空；active relation 数为 219，active input invoice 数与 read-model members 均为 787。
- 关联台 groups list 在 `all`/`2026-05`、`open`/`paired` 下用发票号查询均返回 0；全量翻页也找不到目标组。目标不在 ignored 列表。
- 全局搜索能定位发票并返回 group ID `case:decision:2026-05:oa_invoice_exact_amount:oa-pay-2169:inv_imported_0369`、`zone_hint=open`。
- 对该 group ID 直接调用关联台 `open` 单组详情返回 200/fresh：`group_type=manual_confirmed`、`relation_mode=manual_confirmed`、`reason=existing_case_group`、OA 1 条、发票 1 条、银行流水 0 条、金额检查 matched、active relation metadata 为 true。`all` 与 `2026-05` scope 均可读到该组。
- `WorkbenchReconciliationEngine._auto_create_paired_relations` 以 `decision.decision_key` 作为 `case_id`，同时把关系正式确认为 `relation_mode="manual_confirmed"`；因此正式关系合法保留 `decision:` 来源 ID。
- `PostgresReadModelRepository.get_workbench_groups_page` 对所有 `open` 列表无条件追加 `g.group_id not like 'case:decision:%%'`；随后还用 `_is_workbench_automatic_decision_group()` 仅凭 group/case ID 的 `decision:` 前缀再次丢弃分组。
- `get_workbench_group_detail` 没有上述 `case:decision` 排除，因此形成“单组详情存在、列表查不到”的稳定分叉。
- 现有测试只覆盖真正的 `relation_mode=automatic_decision` fixture，并明确断言 SQL 含 `not like 'case:decision:%%'`；未覆盖 decision-origin ID 已升级为 `manual_confirmed` 的回归场景。
- 全仓扫描确认生产代码中的 `case:decision:` 可见性过滤只位于 `postgres_repositories/read_models.py`；其它 `automatic_decision` 判断属于关系写入 registry、下游 distribution 或投影去污染边界，必须保留且不应改动。
- `_is_workbench_automatic_decision_group()` 只被 groups page 后置过滤和 all-scope aggregate 清理调用；前者与 SQL 前置过滤重复，后者仍需要按当前关系状态正确分类。
- Workbench group payload 已持久化顶层 `relation_mode`，正式化 decision-origin 目标组为 `group_type=manual_confirmed` / `relation_mode=manual_confirmed`；真正旧自动决策组为 candidate/open 且没有正式 mode 或带 `automatic_decision`。
- Groups Redis cache 当前由 active generation 版本与 schema 组成；查询语义变化不应重建 projection，必须 bump/reuse `WORKBENCH_GROUPS_PAGE_CACHE_SCHEMA_VERSION` 并让 API 与 worker warmer 使用同一 schema，避免旧空列表缓存继续遮蔽修复。

# Eliminated

- 非 OA 未同步或完成态别名遗漏：OA 投影存在且原始工作流状态为 completed/已完成。
- 非发票未进入统一事实源：canonical invoice、详情与来源链均存在。
- 非关系事实缺失：active linked/manual relation 存在，进项发票使用情况正是通过该关系展示 OA。
- 非 read model、worker 或 queue 陈旧：两个页面审计均 PASS/fresh，目标 workbench group 位于 active generation。
- 非前端单独漏渲染：后端 groups list 已返回 0，前端没有收到目标组。
- 非月份、ignored 或 paired/open 选择错误：`all` 和 `2026-05` 都受影响；目标未 ignored；因缺少银行流水本应显示在 `open`。

# Resolution

- root_cause: 关联台 `open` 分组列表把 `case_id/group_id` 的历史 `decision:` 前缀当成当前 `automatic_decision` 状态。目标关系已经正式化为 active `manual_confirmed`，但仍被 SQL 前置过滤和 Python 后置分类器误删；单组详情与全局搜索不使用同一过滤条件，所以统一事实、关系和 active generation 都存在，列表却不可见。
- fix: repository groups list SQL 与 all-scope classifier 改为当前 `group_type` / `relation_mode` 优先；`manual_confirmed` decision-origin relation 保留，真正无正式状态或明确 `automatic_decision` / `automatic_match` 的组继续隐藏。删除列表 materialize 后重复 Python filter，避免 count/pagination 与可见集合分叉；API 与 worker warmer 统一使用独立 `WORKBENCH_GROUPS_PAGE_CACHE_SCHEMA_VERSION`，通过 cache miss 恢复列表，不重建或改写事实数据。
- verification: 目标 3 项回归通过；Workbench facade/engine 33 项通过；SQL runtime 204 项通过；全量后端 4459 项通过、33 项既有条件跳过；前端 835 项中一次无关并发时序断言失败，单文件重跑 7/7 通过，生产 build 成功；Playwright smoke 178/178 通过；lint/docs/diff check 通过。生产 release `workbench-520-ec7139bc0-20260714033000`（commit `ec7139bc00c0e3ee061db23fd1a2bed7a2d2d746`）ready/consistent。生产只读断言确认 input-invoice-usage fresh 且唯一返回 `inv_imported_0369` / `520.00` / `oa-pay-2169` / linked；`all` 与 `2026-05` open 各唯一返回正式关系组；paired 各为 0；group detail fresh；OA 原始状态 `completed`、显示 `已完成`、流程请求 ID `2169`。Workbench 与进项发票页面审计最终均为 `integrity=pass`、`freshness=fresh`、`queue=drained`、issues 0；canonical 进项发票与 read-model 成员均为 787，active relation 为 219。
- data_safety: 本修复没有业务写 API、repair SQL、read model rebuild 或 canonical mutation。发布期间两条发布前 processing event 在 300 秒 lease 到期后由 worker 正常重新领取并收敛；最终 audit 证明数据集合、关系边和队列均一致。
- files_changed: `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`、`backend/src/fin_ops_platform/services/workbench_groups_page_cache.py`、`backend/src/fin_ops_platform/app/server.py`、`tests/test_workbench_sql_runtime.py`、`docs/modules/reconciliation-workbench/{README.md,boundary-io.md,state-machine.md,tests.md,implementation-notes.md}`、本诊断记录。
