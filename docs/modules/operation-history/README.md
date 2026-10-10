# 操作历史

入口：`/operations/history`。

提供管理员查询追加型审计事件，按请求聚合业务动作、结果、操作者和固化证据；不修改业务事实。

## 边界与 I/O

输入：管理员 session、分类/结果/日期/人员/页面/search/limit/cursor 或 operation_key。输出：当前页逻辑操作、游标、完整去重操作者选项及 target/artifacts/records/changes/failure、api_calls、activities 与 source 详情。列表不包含 API 明细。

分类为 OA 申请与凭据、App 设置、业务处理、导入与导出、系统任务、未分类。全部筛选按 AND 组合，中文搜索与展示共用已登记操作语义；无登记依据的事件保留未分类，不猜业务动作。limit 必须为 1–200，日期为 YYYY-MM-DD，起止日期按北京时间自然日包含首尾；非法枚举、日期范围和游标返回 400。

页面以分类导航、筛选区和表格组织查询。分类、页面、操作人、结果及北京时间范围组合后点击查询；50/100/200 条游标分页替换当前页。右侧详情抽屉集中展示实际影响、API 调用及直接后续活动，缺少的证据明确显示为未记录。

## 当前业务约定

- 事实源为 audit.events，数据库先按精确 request_id 聚合完整事件再筛选分页。操作者、页面和操作语义取 requested；无 requested 的历史取首个事实。后续领域事件不会覆盖请求身份，也不会改变原操作时间和游标位置。详情在只读一致性快照内读取同一逻辑投影与完整事件。
- 列表、详情与结果筛选共用一套数据库结果投影。没有请求完成证据的旧请求不会因领域事件默认 success 而显示成功；已 requested 的未结束请求超过 5 分钟为 incomplete，尚无 requested/terminal 的历史为 unknown。
- HTTP 202 只证明请求已接收。精确关联的 import_job.completed 及 settings.data_reset.success/failed/partial 可给出后续终态；partial 为 incomplete。OA 附件刷新等未保存关联终态的异步操作明确展示“请求已接收；后续结果未记录”，不读取当前可变任务状态猜历史。
- unsafe 请求及已登记清单下载先记录 requested，审计失败则不执行业务操作；同请求领域事件继承 request ID。普通 GET 查询不写操作历史，现金仍隔离。
- 请求边界固化真实 method/path/status_code/request_id/duration_ms，参数只记录明确白名单的标量摘要，不保存请求正文、响应正文或秘密。旧事件仅展示当时保存的方法、位置和状态；不借当前路由补造 HTTP 方法。
- 导出成功表示文件已生成并返回响应，不表示用户已经保存到电脑。凭据 owner 固化申请人、登录账号、备注变动与删除结果，不返回已保存密码。
- 财务关键字段修正要求事务 actor/reason，并同事务追加 financial_fact_corrections 和 audit，历史不可变。
- 来源证据在写入时固化，查询不依赖可变业务表重造历史；展示过滤 secret、raw payload 和内部标识。
- 收据记录生成及打印请求，不声称实际打印完成；现金操作不进入此历史。
- 列表和详情分别取消过时请求，迟到响应不覆盖当前选择。

## 依赖方向

[权限与审计](../permissions-and-audit/README.md)、[正式关联关系](../workbench-relations/README.md)、[现金账](../cash/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- `backend/src/fin_ops_platform/services/operation_history_semantics.py`：语义与分类登记。
- `backend/src/fin_ops_platform/services/operations_audit_service.py`：查询参数、摘要及详情证据。
- `backend/src/fin_ops_platform/services/postgres_repositories/operations_audit.py`：聚合、筛选、游标、只读详情快照。
- `tests/test_operation_history_postgres.py`：真实 PostgreSQL 结果一致性、异步终态、时区、分页、敏感参数、回滚。
- `tests/test_app_health_api.py`、`tests/test_oa_applicant_credentials_api.py`、`tests/test_import_job_queue.py`：API 边界及 owner 回归。


通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。
