---
status: diagnosed
mode: diagnose-only
created: 2026-09-14
updated: 2026-09-14
---

# 关联确认 503：随机记录 ID 被误解析为月份

## 范围与结论

本轮只分析，不修改实现、测试、生产数据、服务或部署配置。此文件是诊断记录，不替代长期模块合同。

根因已由生产异常栈、当前 canonical 数据及本地调用现有函数三方确认：Application 从任意 row ID 中搜索 `(20\d{2})(\d{2})`，把随机 ID 中的数字当成业务月份。当前截图对应的银行 ID 恰好产生 `2094-40`，repository 再拼成 `2094-40-01`，PostgreSQL 拒绝该非法日期。

## 生产证据

- 请求：`49db15c9841e4a87b69609c32aa54037`。
- 时间：2026-09-14 09:36:04–09:36:05，生产服务器本地时间。
- 运行版本：`main-0c03f9a5-20260914023606`，本地 HEAD 为 `0c03f9a54`。
- Endpoint：`POST /api/workbench/actions/confirm-link`。
- 认证耗时 10.426ms；解析 11 个 selected rows 耗时 63.474ms；请求总耗时 589.094ms，返回 503。
- 异常阶段：`Workbench confirm-link UoW failed at phase=relation_command`。
- 原始异常：`psycopg.errors.DatetimeFieldOverflow: date/time field value out of range: "2094-40-01"`。
- 出错 SQL 参数为 `$5`，对应 relation INSERT 的 `month_scope`。
- 当日截至查询时，日志中同一非法日期异常出现 2 次。

截图的 3 张 OA 分别为 `oa-exp-2231`（52 元）、`oa-exp-2282`（351 元）、`oa-exp-2400`（34 元），合计 437 元。流水为 `txn_imported_b072b36d7209440abc7a5cd65e0a0fd4`，2026-08-20 15:26:06，437 元。查询这些事实只用于核对，不重提确认请求。

## 精确链路

1. `ReconciliationWorkbenchPage.handleSubmitRelationPreview` 向 `confirmWorkbenchLink` 提交 `month=all`、typed row IDs、备注和幂等键。
2. API client 请求 `/api/workbench/actions/confirm-link`。
3. `server.py` 完成 OA 安全门禁和已认证 actor/tenant 解析，调用 action route/facade。
4. `WorkbenchWriteFacade.confirm_link` 加载 canonical rows 并进行金额检查，生产日志证明 11 个成员解析成功。
5. 注入的 `Application._month_scope_for_selected_row_ids` 在 `month=all` 时，调用 `_row_month_scope_from_row_id`；后者使用无边界、无日历校验的正则搜索整个 ID。
6. 银行 ID 包含 `...7[209440]abc...`，生成 `2094-40`。其他没有正则命中的成员被忽略；只要所得集合只有一个值，就把它当作整组关系月份。
7. `WorkbenchWriteUnitOfWork` 中重验 typed selection、进入 relation command、准备 relation/history delta。
8. `PostgresWorkbenchRelationRepository._save_workbench_pair_relations` 把 scope 交给 `common.month_start`；该函数只检查字符串形状，输出 `2094-40-01`。
9. PostgreSQL relation INSERT 失败，异常退出同一事务。该 relation INSERT 在 history append 和 OA payment-status outbox enqueue 之前。
10. facade 的通用异常分支把程序错误转换成 `workbench_state_persistence_unavailable` / 503；前端把该错误显示为通用“服务暂时不可用”，并允许重试。

关键源码位置：

- `backend/src/fin_ops_platform/app/server.py:565`、`:9184`、`:9502`：错误 ID 推断。
- `backend/src/fin_ops_platform/app/server.py:9150`、`:9190`：同类 affected scopes 与 row 日期 fallback。
- `backend/src/fin_ops_platform/services/workbench_write_facade.py:871`：把推断结果传入正式 command。
- `backend/src/fin_ops_platform/services/postgres_repositories/common.py:117`：非严格月份拼接。
- `backend/src/fin_ops_platform/services/postgres_repositories/workbench_relation.py:673`、`:710`：relation INSERT / 日期参数。
- `backend/src/fin_ops_platform/services/workbench_uow.py:69`：同事务边界。
- `backend/src/fin_ops_platform/services/workbench_write_facade.py:824`：异常统一转换为 503。
- `web/src/features/workbench/api.ts:2430`：统一 5xx 文案。
- `web/src/pages/ReconciliationWorkbenchPage.tsx:186`：根据错误消息文本决定是否可重试。

## 本地复现

使用 `object.__new__(Application)` 调用原有纯解析方法，无 Application 启动、无数据库写入：

```text
oa-exp-2231 -> None
oa-exp-2282 -> None
oa-exp-2400 -> None
txn_imported_b072b36d7209440abc7a5cd65e0a0fd4 -> 2094-40
_month_scope_for_selected_row_ids(month="all", row_ids=上述四个ID) -> 2094-40
month_start("2094-40") -> 2094-40-01
```

合成随机 ID 含 `202608` 时会被当作合法 `2026-08`；含 `202613` 时产生非法 `2026-13`。因此仅限制月份为 01–12 不能消除随机 ID 被误认成真实日期的问题。

Git 记录表明这组 ID 正则及其推断逻辑于 `d4781f1c4`（2026-04-08）引入，并仍被当前人工确认路径调用。可以确认这是旧逻辑延续，不能由此推断首次用户受影响的时间。

## 数据一致性与存量影响

生产检查使用 `REPEATABLE READ READ ONLY`，连接设置只读、5 秒 statement timeout，不加载 Application，不执行写命令。

截图失败结果：

- 3 个 OA 与该银行记录当前 active owner 均为空。
- 该银行记录在全部 relation 中命中数为 0。
- 包含该银行 ID 的幂等请求记录数为 0。
- 与生产异常点、UoW 回滚逻辑一致；没有把“操作后”预览误当成已提交事实。

存量扫描（查询时快照）：

- relation 总数 899；非空月份除 2026-01 至 2026-09 外，还发现 `2097-03-01`。
- `CASE-AUTO-0213`：active，错误月份为 `2097-03-01`。
- `CASE-AUTO-0210`：cancelled，同样为 `2097-03-01`。
- 这两条关系相关银行事实的交易日期为 2026-08-21；其银行 ID `txn_imported_00bb0f7977e847d494302097037b09b5` 含 `209703`，精确解释错误月份。
- 上述两个 case 的 4 条 relation history 记录包含 `2097-03`。
- 3 条 committed idempotency response 的 affected_months 含 `2097-03`：confirm_link 2 条、withdraw_link 1 条。
- 1275 条未删除银行记录中，8 个 ID 命中旧正则，7 个结果月份非法；1293 条未删除发票中 1 个 ID 命中、月份合法。这是风险候选数，不表示全部已经失败，触发还取决于入口、选择集合及请求 scope。

没有把其他 2026 年合法月份记录全部逐条重新计算，因此不把两条已证实异常宣称为所有可能错误。完整存量修复前需比较成员 canonical dates、关系 metadata、history 恢复来源和幂等响应；不能只筛选未来年份。

## 影响边界

- 直接 owner：reconciliation-workbench、workbench-relations。
- 共用 ID 推断的确认预览、确认、取消、撤回 scope 计算、个人垫付关联，以及旧 cash special relation helper 都需检查；此处 cash special 是关联台既有特殊关系链，不是独立 `cash.*` 模块。
- `affected_scope_keys/affected_months` 同时合并 canonical 日期和 ID 推断，真实日期存在也可能混入伪月份。
- `_row_month_scope` 在日期字段缺失时仍回退 ID；OA 日期只检查部分嵌套字段，需要对照当前 canonical DTO 的顶层 application_date 等字段。
- relation scope 被 direct query 的 seed/filter 和发票 scope 扩展消费，command 撤回/历史恢复及幂等响应也读取 scope；不是只影响错误提示。
- 当前 Workbench 页面是 canonical direct GET，不拥有 read-model refresh worker。OA payment-status event 是关系写入后的事务事件，此次异常发生在其 enqueue 前。
- `common.month_start` 是多 repository 共用函数。若修改其全局合同，需要覆盖 OA、ETC、税金及其他调用方；优先把 relation scope 修复限制在本 owner 的清晰边界，再决定公共 helper 是否需要另行兼容性验证。

## 修复方案（尚未实施）

1. 移除 Workbench 写链路从任意 row ID 搜索月份的旧逻辑、注入回调和 fallback。ID 只用来查 canonical 事实，不能承载隐式业务日期。
2. preview、confirm、cancel/withdraw、相关特殊关系共用有明确输入的 canonical scope 解析。优先复用已加载的 typed rows；只在确有缺项时批量读取，不新增逐行查询。明确单月、跨月、无有效日期、ETC summary 和 OA in-progress 的规则；跨月保留既有 `all` 表达，真实 affected months 单独返回，不能以第一个数字或第一条流水替代整组范围。
3. 在提交 UoW 内基于本次有效 canonical facts 形成 scope，并让金额/关系历史校验使用一致事实。relation command/repository 写入前执行真实日历校验，非法请求与内部错误使用稳定错误类型，避免程序错误被当成可重试的临时数据库故障。仓库已有 `workbench_filter_options.normalize_workbench_scope_key`，同时校验 01–12 与真实年月；selection repository 已使用它，当前推断后传给 relation INSERT 的 scope 绕过了这一校验。实施优先复用现有校验合同，不另写宽松日期解析器。
4. 同时修复 affected scopes、撤回恢复与幂等 replay 的传播路径。已证明有错误的历史 metadata 必须有审计、可回滚的修复方案；保留原始历史证据，不直接改写审计历史或清空幂等表。确定历史 snapshot 的纠正/恢复规则后再执行数据修复。
5. 日志记录应直接包含 request ID、失败阶段和稳定错误分类。现有 deploy helper `api_request_error/api_request_trace` 取最后一个 request-ID 行，误取 request_total 并只向后输出，需改成查匹配异常事件及其 stack；这是诊断链缺陷。
6. 前端按结构化错误码区分重试/重新预览/联系管理员，保留备注和 request ID。保留已有“已提交但 GET 失败不得再次提交”的保护，不增加本地挪行逻辑。

不采用：把 40 改成 04、捕获异常后随意写当前月份、只增加正则月范围、无条件返回 all、删除幂等保护、重新引入 read model 或部署重启作为修复。

## 验证与测试缺口

已运行：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract tests.test_workbench_auth_context_idempotency tests.test_workbench_relation_command_service -q
# 77 tests OK
cd web && npm test -- --run src/test/WorkbenchApi.test.ts
# 75 tests passed
```

另执行了原有解析函数精确复现、生产只读 GET、只读 SQL、请求时序/完整异常栈读取、当日异常计数、whole-repo 相关字符串扫描及 Git 来源追踪。

测试漏网证据：`tests/test_workbench_auth_context_idempotency.py:676` 把真实月份计算注入为固定 `2026-05`，对应 scope 回调也默认固定值；现有 facade/UoW 测试没有覆盖 Application 的 ID 月份推断。前端测试 `WorkbenchSelection.test.tsx:1194` 专门断言该类 503 提示及可重试按钮，不能证明真实数据库关系写入成功。

实施时七类测试责任：

| 类别 | 必须覆盖 |
| --- | --- |
| 业务单元 | 随机 ID 含非法/合法月份、多个命中、单月/跨月、空值、日期边界，ID 改变不影响月份 |
| 服务/持久化 | 真实 scope 解析与 UoW 集成、无半写、history/audit/幂等一致性、历史纠正与 rollback |
| API | 3 OA + 1 bank + 7 invoice 确认成功；非法字段、权限、并发冲突和稳定错误 envelope |
| 缓存/后台任务 | 不新增 read model/cache；验证既有 OA 支付状态 outbox 只在成功提交后产生、失败零事件 |
| 前端交互 | 成功一次 POST + 一次 GET；结构化错误重试、保留备注、已提交后读失败不重复提交 |
| 端到端 | 随机 ID 多对一确认 → 页面回读 → 下游读取 → 撤回 → 恢复；实际 PostgreSQL 运行 |
| 旧功能回归 | 撤回/取消/个人垫付/特殊关系、ETC、跨月查询、历史恢复及幂等重放；如改公共日期 helper 额外覆盖全部消费者 |

本轮未新增或修改测试。未运行新的真实 PostgreSQL 写入回归、生产提交/撤回、迁移或存量修复，符合只诊断要求；当前环境未设置 `FIN_OPS_TEST_DATABASE_URL`。已通过测试不代表修复完成。

## 文档影响与下一步

实施将改变 scope 事实来源、写入边界错误合同、测试矩阵和存量修复方式，需要同步 reconciliation-workbench / workbench-relations 的 boundary-io、state-machine、tests，以及相关长期 API/运维合同。现有部分模块文档仍包含已退役 read-model 叙述，不能把这些历史内容重新用于本次设计。

本轮只新增本诊断记录。下一步应按上述已验证根因制定有限实现计划，先补真实解析/数据库失败回归，再实现、核对存量纠正方案和验证；用户尚未要求进入实现。
