# fin-ops-platform

以银企核销（Reconciliation）为切入点的财务运营平台，后续预留：

- OA 系统接入
- 项目成本测算（Project Costing）

## 当前仓库结构

- [`docs/`](/Users/yu/Desktop/fin-ops-platform/docs/README.md)：业务需求、架构方案、路线图、任务拆解
- [`docs/product/`](/Users/yu/Desktop/fin-ops-platform/docs/product/银企核销需求.md)：产品需求源文档
- [`docs/architecture/`](/Users/yu/Desktop/fin-ops-platform/docs/architecture/OA%20集成当前%20app%20技术方案.md)：跨系统集成与总体方案
- [`fixtures/`](/Users/yu/Desktop/fin-ops-platform/fixtures/README.md)：导入样例、测试数据、手工验收 Excel
- `backend/`：Python 后端与导入解析服务
- `web/`：正式 React 前端工程
- `tests/`：基础单元测试
- `prompts/`：分阶段开发 prompt

## 本地依赖

导入正式化已引入真实 Excel 解析依赖：

```bash
python -m pip install -r backend/requirements.txt
```

本地如需启用真实 OA MongoDB 接入，可在 runtime 目录放置：

- `.runtime/fin_ops_platform/oa_mongo_config.json`

当前代码也支持环境变量覆盖：

- `FIN_OPS_OA_MONGO_HOST`
- `FIN_OPS_OA_MONGO_PORT`
- `FIN_OPS_OA_MONGO_DATABASE`
- `FIN_OPS_OA_MONGO_USERNAME`
- `FIN_OPS_OA_MONGO_PASSWORD`
- `FIN_OPS_OA_MONGO_AUTH_SOURCE`
- `FIN_OPS_OA_PAYMENT_FORM_ID`
- `FIN_OPS_OA_EXPENSE_FORM_ID`
- `FIN_OPS_OA_PROJECT_FORM_ID`

## Prompt 01 已落地内容

- 核心领域模型：客商、发票、银行流水、核销单、核销明细、台账、导入批次、审计日志
- 关键状态枚举：发票、流水、台账、核销单、导入批次
- 最小 HTTP 服务：`/health`、`/foundation/seed`
- 审计服务与示例 seed 数据

## Prompt 02 已落地内容

- 导入预览接口：`POST /imports/preview`
- 导入确认接口：`POST /imports/confirm`
- 导入批次查询接口：`GET /imports/batches/{batch_id}`
- 导入标准化逻辑：日期、金额、名称、方向规范化
- 幂等防重：唯一业务主键 + 数据指纹
- 导入逐行判定：新增、状态更新、重复跳过、疑似重复、异常
- 导入批次与逐行结果模型
- JSON 行数据样例说明文档

## Prompt 03 已落地内容

- 自动匹配运行接口：`POST /matching/run`
- 匹配结果列表接口：`GET /matching/results`
- 匹配结果详情接口：`GET /matching/results/{result_id}`
- 匹配结果模型与匹配运行模型
- 已实现规则：
  - 标准一对一自动匹配
  - 多票一付 / 一票多付建议
  - 部分核销建议
  - 待人工处理分流
- 匹配解释信息、规则码和置信度输出

## Prompt 04 已落地内容

- 人工核销工作台接口：`GET /workbench`
- 人工核销动作接口：
  - `POST /workbench/actions/confirm`
  - `POST /workbench/actions/exception`
  - `POST /workbench/actions/offline`
- 核销单查询接口：
  - `GET /reconciliation/cases`
  - `GET /reconciliation/cases/{case_id}`
- 工作台原型页面服务：`GET /workbench/prototype`
- 已落地能力：
  - `ReconciliationCase + ReconciliationLine` 人工核销落单
  - `SO-* / PI-*` 结构化异常处理
  - 线下核销记录 `offline_record`
  - 审计日志落地
  - 工作台银行 / 发票真实接口接入
  - 右侧上下文操作区与详情弹窗分离
  - CORS 与 `OPTIONS` 支持，便于本地预览服务联调

## Prompt 05 已落地内容

- 台账接口：
  - `GET /ledgers`
  - `GET /ledgers/{ledger_id}`
  - `POST /ledgers/{ledger_id}/status`
- 提醒接口：
  - `GET /reminders`
  - `POST /reminders/run`
- 已落地能力：
  - 核销动作自动生成 `FollowUpLedger`
  - 已支持台账类型：催款、催票、退款、预收、预付、待开销项票、待付款提醒、外部往来、非税收入
  - 支持预计处理日期、责任人、状态、跟进备注
  - 支持即将到期与已逾期视角
  - 提醒去重与重复执行保护
  - 工作台原型已新增 `台账提醒` 页面，可直接查看台账、执行提醒、更新状态

## Prompt 06 已落地内容

- 高阶异常动作接口：
  - `POST /workbench/actions/difference`
  - `POST /workbench/actions/offset`
- 已落地能力：
  - 差额核销，支持结构化差额原因：手续费、抹零、汇率差、税差、其他
  - 红字发票参与工作台核销，并支持反向流水闭环
  - `OffsetNote` 内部抵扣单，不依赖真实银行流水
  - 工作台右侧操作区已新增 `差额核销` 与 `内部抵扣`
  - 健康检查中已暴露 `advanced_exceptions` 能力

## Prompt 07 已落地内容

- OA 集成接口：
  - `GET /integrations/oa`
  - `POST /integrations/oa/sync`
  - `GET /integrations/oa/sync-runs`
  - `GET /integrations/oa/sync-runs/{run_id}`
- 已落地能力：
  - 独立 `Integration Hub`，OA 逻辑不侵入核心核销服务
  - `Mock OA` 适配器，覆盖客商、项目、审批单、付款申请、报销单
  - 已新增 `MongoOAAdapter`，可从真实 `form_data` 集合读取支付申请、日常报销和项目主数据
  - `IntegrationMapping + IntegrationSyncRun + IntegrationSyncIssue` 模型
  - 已存在客商可按名称挂接 `oa_external_id`
  - 工作台原型已新增只读 `OA 同步` 视图，可执行同步和重试
  - 健康检查中已暴露 `oa_integration_foundation` 能力

## OA 页面壳体 / 登录复用接入方案

已新增一套基于真实 OA 源码分析的接入文档，用于把当前 app 放到公司 OA 页面下，并复用 OA 登录与菜单权限：

- 总方案：[OA 集成当前 app 技术方案.md](/Users/yu/Desktop/fin-ops-platform/docs/architecture/OA%20%E9%9B%86%E6%88%90%E5%BD%93%E5%89%8D%20app%20%E6%8A%80%E6%9C%AF%E6%96%B9%E6%A1%88.md)
- 菜单接入说明：[oa-menu-iframe-integration.md](/Users/yu/Desktop/fin-ops-platform/docs/dev/oa-menu-iframe-integration.md)
- 设计文档：[2026-04-03-oa-shell-auth-visibility-design.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/specs/2026-04-03-oa-shell-auth-visibility-design.md)
- 实施计划：[2026-04-03-oa-shell-auth-visibility.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/plans/2026-04-03-oa-shell-auth-visibility.md)
- Prompt 28：[28-oa-shell-auth-foundation.md](/Users/yu/Desktop/fin-ops-platform/prompts/28-oa-shell-auth-foundation.md)
- Prompt 29：[29-oa-menu-iframe-integration.md](/Users/yu/Desktop/fin-ops-platform/prompts/29-oa-menu-iframe-integration.md)
- Prompt 30：[30-oa-visibility-and-access-control.md](/Users/yu/Desktop/fin-ops-platform/prompts/30-oa-visibility-and-access-control.md)
- Prompt 31：[31-oa-integration-deployment-and-qa.md](/Users/yu/Desktop/fin-ops-platform/prompts/31-oa-integration-deployment-and-qa.md)
- 访问账户分层权限设计：[2026-04-07-oa-access-role-management-design.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/specs/2026-04-07-oa-access-role-management-design.md)
- 访问账户分层权限计划：[2026-04-07-oa-access-role-management.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/plans/2026-04-07-oa-access-role-management.md)
- Prompt 35：[35-oa-access-role-backend-foundation.md](/Users/yu/Desktop/fin-ops-platform/prompts/35-oa-access-role-backend-foundation.md)
- Prompt 36：[36-oa-access-role-ui-and-action-gating.md](/Users/yu/Desktop/fin-ops-platform/prompts/36-oa-access-role-ui-and-action-gating.md)
- Prompt 37：[37-oa-access-role-sync-and-qa.md](/Users/yu/Desktop/fin-ops-platform/prompts/37-oa-access-role-sync-and-qa.md)
- 部署说明：[deploy/oa/README.md](/Users/yu/Desktop/fin-ops-platform/deploy/oa/README.md)
- Nginx 示例：[deploy/oa/nginx.fin-ops.conf.example](/Users/yu/Desktop/fin-ops-platform/deploy/oa/nginx.fin-ops.conf.example)
- 环境模板：[deploy/oa/fin_ops.env.example](/Users/yu/Desktop/fin-ops-platform/deploy/oa/fin_ops.env.example)
- 菜单 SQL：[deploy/oa/fin_ops_menu.mysql.sql](/Users/yu/Desktop/fin-ops-platform/deploy/oa/fin_ops_menu.mysql.sql)
- 角色绑定 SQL：[deploy/oa/fin_ops_role_binding.mysql.sql](/Users/yu/Desktop/fin-ops-platform/deploy/oa/fin_ops_role_binding.mysql.sql)
- 用户角色同步 SQL：[deploy/oa/fin_ops_user_role_sync.mysql.sql](/Users/yu/Desktop/fin-ops-platform/deploy/oa/fin_ops_user_role_sync.mysql.sql)

## Prompt 30 已落地内容

- `finops:app:view` 作为统一访问口径
- `GET /api/session/me` 继续用于会话识别和前端 `403` 展示
- 所有核心业务接口现在都要求有效 OA 会话与访问授权：
  - `/api/*`
  - `/imports/*`
  - `/matching/*`
  - `/workbench*`
  - `/integrations/*`
  - `/projects*`
  - `/ledgers*`
  - `/reminders*`
  - `/reconciliation/*`
- 未登录或 token 失效：返回 `401`
- 已登录但无权限：返回 `403`
- 不再依赖“只隐藏菜单”的前端可见性控制

## Prompt 31 已落地内容

- OA 集成已经补齐真实部署资产：
  - `/fin-ops/`
  - `/fin-ops-api/`
- 已新增：
  - 同域部署与回滚文档
  - OA 集成环境变量模板
  - Nginx 反向代理示例
- 已补齐发布顺序：
  - 后端
  - 前端
  - 权限
  - 菜单
  - 联调
- 已补齐联调验收清单：
  - 登录复用
  - 菜单可见性
  - 403 拦截
  - workbench / tax / cost / export / search 可用性
- 已补齐关键鉴权链路测试：
  - `Admin-Token` cookie 复用
  - `session/me`
  - 受保护 API 的 `401/403`

## Prompt 37 已落地内容

- OA 菜单可见性同步口径已升级为三类账户模型：
  - `不可见`
  - `只可看和只可导出`
  - `所有操作均可`
  - 管理员固定为 `YNSYLP005`
- 部署文档已明确：
  - `allowed_usernames` 之外的账户必须在 OA 菜单中也不可见
  - `readonly_export_usernames` 与全操作用户都属于可访问账户
  - app 设置保存后，还需要手工同步 OA 用户角色
- 已补充：
  - OA 角色绑定 SQL 模板升级
  - OA 用户角色同步 SQL 模板
  - 分账户类型 QA 清单
  - 自动化回归建议

## 关联台性能重构新方向

针对当前 `确认关联 / 取消配对` 和整页 `关联台 load` 的性能问题，已新增一套“`pair relations + 物化 read model`”方案：

- 新设计文档：[2026-04-08-workbench-materialized-read-model-design.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/specs/2026-04-08-workbench-materialized-read-model-design.md)
- 新实施计划：[2026-04-08-workbench-materialized-read-model.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/plans/2026-04-08-workbench-materialized-read-model.md)
- Prompt 41：[41-workbench-read-model-foundation.md](/Users/yu/Desktop/fin-ops-platform/prompts/41-workbench-read-model-foundation.md)
- Prompt 42：[42-workbench-read-model-actions-and-refresh.md](/Users/yu/Desktop/fin-ops-platform/prompts/42-workbench-read-model-actions-and-refresh.md)
- Prompt 43：[43-workbench-read-model-ui-perf-and-qa.md](/Users/yu/Desktop/fin-ops-platform/prompts/43-workbench-read-model-ui-perf-and-qa.md)

目标是：

- `确认关联 / 取消配对` 只改最小写模型
- 关联台加载优先读取缓存好的快照
- 前端动作成功后立即局部更新，后台再静默刷新兜底

## OA 权限模型后续升级方向

当前仓库已经补了一版更细的权限重构方案，用于替换“只有单一 `finops:app:view`”的旧口径。目标模型是：

- 不可见且不可访问
- 可见且可访问，但细分为：
  - `所有操作均可`
  - `只可看和只可导出`
- 只有 `YNSYLP005` 可管理权限

后续开发入口：

- [35-oa-access-role-backend-foundation.md](/Users/yu/Desktop/fin-ops-platform/prompts/35-oa-access-role-backend-foundation.md)
- [36-oa-access-role-ui-and-action-gating.md](/Users/yu/Desktop/fin-ops-platform/prompts/36-oa-access-role-ui-and-action-gating.md)
- [37-oa-access-role-sync-and-qa.md](/Users/yu/Desktop/fin-ops-platform/prompts/37-oa-access-role-sync-and-qa.md)

## 关联台动作性能重构后续方向

当前仓库已经补了一版“pair relations 轻量写模型”方案，用于替换把配对关系混在 row overrides 里的旧口径。目标模型是：

- 配对关系进入独立 `workbench_pair_relations`
- `确认关联 / 取消配对` 只改 pair relation
- 前端在后端成功后立即局部更新，后台静默刷新兜底
- 自动工资 / 内部往来款逐步统一进入同一关系层

后续开发入口：

- [38-workbench-pair-relations-foundation.md](/Users/yu/Desktop/fin-ops-platform/prompts/38-workbench-pair-relations-foundation.md)
- [39-workbench-pair-relations-actions-and-read-model.md](/Users/yu/Desktop/fin-ops-platform/prompts/39-workbench-pair-relations-actions-and-read-model.md)
- [40-workbench-pair-relations-ui-perf-and-qa.md](/Users/yu/Desktop/fin-ops-platform/prompts/40-workbench-pair-relations-ui-perf-and-qa.md)

## Prompt 08 已落地内容

- 项目接口：
  - `GET /projects`
  - `GET /projects/{project_id}`
  - `POST /projects`
  - `POST /projects/assign`
- 已落地能力：
  - 独立 `ProjectCostingService`，负责项目归属解析、人工归属、项目汇总查询
  - 新增 `ProjectAssignmentRecord`，支持人工指定项目归属并保留审计轨迹
  - 新增 `ProjectSummary`，按项目汇总收入、支出、已核销、未闭环金额
  - 项目归属优先级固定为：手动指定 > OA 单据带出的项目 > 对象已有 `project_id` > 无归属
  - 发票、流水、核销单、台账已可在项目维度归集
  - 工作台原型已新增最小 `项目归集` 页面，可创建项目并执行对象归属
  - 健康检查中已暴露 `project_costing_foundation` 能力

## Prompt 09 已落地内容

- 正式前端工程：
  - `web/package.json`
  - `web/src/main.tsx`
  - `web/src/app/App.tsx`
  - `web/src/app/router.tsx`
- 已落地能力：
  - 使用 `Vite + React + TypeScript` 建立 Workbench V2 前端骨架
  - 已提供两个页面路由：
    - `OA & 银行流水 & 进销项发票关联台`
    - `销项票税金 - 进项票税金`
  - 已建立共享月份上下文，切页后月份保持一致
  - 已把现有原型的页面壳体迁入 React 工程，并继续保留原型文件作为参考
  - 当前先使用本地 mock 数据，不接后端
  - 已新增基础前端测试与构建脚本

## Prompt 10 已落地内容

- 工作台组件：
  - `web/src/components/workbench/PaneTable.tsx`
  - `web/src/components/workbench/ResizableTriPane.tsx`
  - `web/src/components/workbench/WorkbenchZone.tsx`
  - `web/src/hooks/useResizablePanes.ts`
- 已落地能力：
  - 主工作台已拆成 `已配对 / 未配对` 两个独立 zone
  - 每个 zone 内支持 `OA / 银行流水 / 进销项发票` 三栏独立拖拽
  - splitter 可拖到 `0` 宽并收起栏位
  - 每个 zone 头部按钮可独立收起 / 恢复当前 zone 的栏位
  - 仅在当前可见栏之间显示 splitter
  - 各栏内容独立滚动，表头 sticky 固定
  - 已新增组件测试覆盖收起、恢复和拖拽到 `0`

## Prompt 11 已落地内容

- 工作台交互组件：
  - `web/src/components/workbench/RowActions.tsx`
  - `web/src/components/workbench/DetailDrawer.tsx`
  - `web/src/hooks/useWorkbenchSelection.ts`
- 已落地能力：
  - 点击行只更新选中状态，不自动弹出详情
  - 同 `caseId` 的记录在整个工作台页面内联动高亮
  - 当前选中行和候选联动行有清晰视觉差异
  - 每行已新增 `详情` 按钮
  - 详情仅通过行内按钮打开右侧抽屉
  - 抽屉已支持 OA / 银行流水 / 发票三类 mock 详情展示
  - 已新增交互测试覆盖“点行不弹详情”“点详情才开抽屉”和“抽屉可关闭”

## Prompt 12 已落地内容

- 工作台字段与动作组件：
  - `web/src/features/workbench/tableConfig.ts`
  - `web/src/components/workbench/PaneTable.tsx`
  - `web/src/components/workbench/RowActions.tsx`
  - `web/src/components/workbench/DetailDrawer.tsx`
- 已落地能力：
  - OA / 银行流水 / 发票三栏已按需求文档切成真实主表字段列
  - 三栏表格已支持更宽的横向滚动口径，适配 Excel 风格信息密度
  - 银行流水行内已提供 `详情 + 更多`，下挂 `关联情况 / 取消关联 / 异常处理`
  - 未配对 OA / 发票行内已提供 `详情 + 确认关联 + 标记异常`
  - 详情弹窗的主表字段已与三栏列定义对齐，银行 / 发票补充展示详情字段
  - 当前行内动作仍为前端 mock 回调，页面会回显动作提示，后续再接真实接口

## Prompt 13 已落地内容

- 税金抵扣组件：
  - `web/src/components/tax/TaxSummaryCards.tsx`
  - `web/src/components/tax/TaxTable.tsx`
  - `web/src/components/tax/TaxResultPanel.tsx`
- 已落地能力：
  - `税金抵扣` 页面已切成按月份驱动的独立工作台
  - 销项票开票情况只读展示，进项票认证计划支持勾选试算
  - 右侧 `已认证结果` 抽屉展示已匹配计划和未进入计划的已认证票
  - `已认证发票导入` 已接入真实预览 / 确认导入链路，导入后会刷新摘要、计划锁灰状态和抽屉
  - 销项税额、已认证进项税额、计划进项税额、本月抵扣额、应纳税额 / 留抵税额会随当前状态重算

## Prompt 14 已落地内容

- Workbench V2 后端契约模块：
  - `backend/src/fin_ops_platform/services/workbench_query_service.py`
  - `backend/src/fin_ops_platform/services/workbench_action_service.py`
  - `backend/src/fin_ops_platform/services/tax_offset_service.py`
  - `backend/src/fin_ops_platform/services/oa_adapter.py`
  - `backend/src/fin_ops_platform/services/mongo_oa_adapter.py`
  - `backend/src/fin_ops_platform/services/bank_account_resolver.py`
  - `backend/src/fin_ops_platform/app/routes_workbench.py`
  - `backend/src/fin_ops_platform/app/routes_tax.py`
- 已落地能力：
  - 新增 `GET /api/workbench?month=YYYY-MM`
  - 新增 `GET /api/workbench/rows/{row_id}`
  - 新增 `POST /api/workbench/actions/confirm-link`
  - 新增 `POST /api/workbench/actions/mark-exception`
  - 新增 `POST /api/workbench/actions/cancel-link`
  - 新增 `POST /api/workbench/actions/update-bank-exception`
  - 新增 `GET /api/tax-offset?month=YYYY-MM`
  - 新增 `POST /api/tax-offset/calculate`
  - 已提供 `2026-03 / 2026-04` 两个月份种子数据
  - 三类行详情已拆成独立接口，动作接口统一返回结果结构
  - OA adapter 与 Mongo OA adapter 边界已落位，银行账户识别已独立封装
  - 现阶段 React 前端还没有切到这些 `/api/*` 接口，真实联调留给 Prompt 15

## Prompt 15 已落地内容

- Workbench V2 前端联调模块：
  - `web/src/features/workbench/types.ts`
  - `web/src/features/workbench/api.ts`
  - `web/src/features/tax/types.ts`
  - `web/src/features/tax/api.ts`
  - `web/src/pages/ReconciliationWorkbenchPage.tsx`
  - `web/src/pages/TaxOffsetPage.tsx`
- 已落地能力：
  - React 工作台已切到真实 `GET /api/workbench?month=YYYY-MM`
  - 工作台详情弹窗已改成点击 `详情` 后按行请求 `GET /api/workbench/rows/{row_id}`
  - 行内动作已接真实接口：
    - `POST /api/workbench/actions/confirm-link`
    - `POST /api/workbench/actions/mark-exception`
    - `POST /api/workbench/actions/cancel-link`
    - `POST /api/workbench/actions/update-bank-exception`
  - 月份切换会驱动工作台和税金页重新请求后端
  - 税金页已切到真实接口：
    - `GET /api/tax-offset?month=YYYY-MM`
    - `POST /api/tax-offset/calculate`
  - 工作台和税金页都已补 `loading / empty / error` 状态
  - Vite dev server 已增加 `/api` 代理，默认转发到 `http://127.0.0.1:8001`
  - 已新增前端集成测试，覆盖真实 fetch、月份联动、详情按需加载、税金重算、空态和错态

## 导入正式化 A 已落地内容

- 后端真实文件导入接口：
  - `POST /imports/files/preview`
  - `POST /imports/files/confirm`
  - `GET /imports/files/sessions/{session_id}`
  - `GET /imports/templates`
  - `POST /imports/files/retry`
  - `GET /imports/batches/{batch_id}/download`
  - `POST /imports/batches/{batch_id}/revert`
- 已支持真实模板自动识别：
  - 发票导出
  - 工商银行流水
  - 光大银行流水
  - 建设银行流水
  - 民生银行流水
  - 平安银行流水
- 已落地能力：
  - 支持一次上传多份 `.xlsx / .xls` 文件
  - 后端统一做模板识别、解析、逐文件预览和确认入库
  - 文件级失败不会阻断同批次其他文件
  - 导入会话、预览结果、发票、银行流水和匹配运行已支持 Mongo 持久化，服务重启后不会丢失
  - 发票导入已支持自动区分 `input_invoice / output_invoice`，并支持在导入中心手动切换后重试
  - React 前端已新增 `导入中心` 页面，支持批量上传、模板库查看、逐文件预览、逐行判定查看、手动改判、勾选确认导入、批次下载与撤销
  - 原始上传文件已迁入 Mongo GridFS，不再依赖本地 `import_files/`
  - 确认导入后会自动触发匹配引擎，工作台回到对应月份会直接读取实时导入数据
  - Vite 已新增 `/imports` 代理，开发模式下可直接联调后端

## 成本统计页面规划与落地进度

- 新页面入口：`成本统计`
- 入口位置：顶部导航，位于 `税金抵扣` 右侧
- 页面定位：
  - 基于已关联 OA 成本字段的支出银行流水做统计
  - 支持按月份查看、按项目下钻、下钻到具体流水
  - 支持导出当前视图
- 相关文档：
  - [成本统计开发说明](/Users/yu/Desktop/fin-ops-platform/docs/dev/cost-statistics-workbench.md)
  - [成本统计设计文档](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/specs/2026-04-01-cost-statistics-workbench-design.md)
  - [项目明细强导出设计文档](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/specs/2026-04-01-cost-statistics-project-export-design.md)
  - [成本统计实施计划](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/plans/2026-04-01-cost-statistics-workbench.md)
- 对应 prompt：
  - [Prompt 16](/Users/yu/Desktop/fin-ops-platform/prompts/16-cost-statistics-backend-foundation.md)
  - [Prompt 17](/Users/yu/Desktop/fin-ops-platform/prompts/17-cost-statistics-page-and-drilldown.md)
  - [Prompt 18](/Users/yu/Desktop/fin-ops-platform/prompts/18-cost-statistics-export-and-qa.md)
  - [Prompt 19](/Users/yu/Desktop/fin-ops-platform/prompts/19-project-detail-export-foundation.md)
  - [Prompt 20](/Users/yu/Desktop/fin-ops-platform/prompts/20-project-detail-export-ux.md)
  - [Prompt 21](/Users/yu/Desktop/fin-ops-platform/prompts/21-project-detail-export-history-and-qa.md)

## Prompt 16 已落地内容

- 成本统计后端模块：
  - `backend/src/fin_ops_platform/services/cost_statistics_service.py`
- 已落地能力：
  - 新增 `GET /api/cost-statistics?month=YYYY-MM`
  - 新增 `GET /api/cost-statistics/projects/{project_name}?month=YYYY-MM`
  - 新增 `GET /api/cost-statistics/transactions/{transaction_id}`
  - 统计以**支出类银行流水**为主数据源
  - 仅统计已能取得 OA `项目名称 / 费用类型 / 费用内容` 的流水
  - 支持月份汇总、项目明细、具体流水详情三层只读查询
  - Mongo OA 适配层已补 `费用类型 / 费用内容` 结构化字段
  - 健康检查中已暴露 `cost_statistics_foundation` 能力

## Prompt 17 已落地内容

- React 前端已新增 `成本统计` 顶部导航入口：
  - 路由：`/cost-statistics`
- 已落地的前端交互：
  - 默认进入 `按时间`
  - `按时间` 和 `按费用类型` 支持单月或区间
  - `按项目` 默认全部期间
  - `按项目` 改成从左到右 `项目 -> 费用类型 -> 流水`
  - 点击月份汇总行可下钻到项目明细
  - 点击项目明细行可继续下钻到具体流水详情
  - 页面内通过面包屑和返回路径完成下钻，不使用弹窗承载主流程
  - 已补 `loading / empty / error` 状态
- 本轮未做：
  - 趋势分析
  - 多维筛选器

## Prompt 18 已落地内容

- 成本统计导出链路已打通：
  - 新增 `GET /api/cost-statistics/export`
  - 支持 `month / project / transaction` 三种当前视图导出
  - 导出格式为 `xlsx`
- 导出文件名规则：
  - 月份汇总：`成本统计_{month}_月份汇总.xlsx`
  - 项目明细：`成本统计_{month}_项目明细_{project}.xlsx`
  - 流水详情：`成本统计_{month}_流水详情_{project}_{transactionId}.xlsx`
- React 前端已补齐：
  - 当前层级导出按钮
  - 导出中的 loading 文案
  - 导出成功反馈
  - 导出失败反馈
- 验证已完成：
  - 前端：`cd web && npm run test -- --run`
  - 前端构建：`cd web && npm run build`
  - 后端：`PYTHONPATH=backend/src python3 -m unittest discover -s tests -v`

## Prompt 19 已落地内容

- 项目明细强导出后端底座已落地：
  - 新增 [ProjectDetailExportService](/Users/yu/Desktop/fin-ops-platform/backend/src/fin_ops_platform/services/project_detail_export_service.py)
  - `view=project` 的导出已从单 sheet 升级为多 sheet 工作簿
- 当前项目导出工作簿包含：
  - `导出说明`
  - `项目汇总`
  - `按费用类型汇总`
  - `按费用内容汇总`
  - `流水明细`
  - `OA关联明细`
  - `发票关联明细`
  - `异常与未闭环`
- 保持现有导出入口兼容：
  - `GET /api/cost-statistics/export?view=project...`
- 已补测试：
  - [test_project_detail_export_service.py](/Users/yu/Desktop/fin-ops-platform/tests/test_project_detail_export_service.py)
  - [test_cost_statistics_api.py](/Users/yu/Desktop/fin-ops-platform/tests/test_cost_statistics_api.py)

## Prompt 20 已落地内容

- 成本统计页导出入口已统一成 `导出中心`
- `导出中心` 弹窗支持：
  - `按时间`
  - `按项目`
  - `按费用类型`
- `按时间` 支持：
  - 自定义月份
  - 自定义时间区间（精确到日）
- `按项目` 支持：
  - 项目选择
  - 费用类型多选 / 全选 / 清空
  - 默认全部期间
- `按费用类型` 支持：
  - 费用类型多选 / 全选 / 清空
  - 当前月份
  - 自定义时间区间（精确到日）
- `仅预览` 会展示：
  - 预计导出条数
  - 预计 sheet 数
  - 金额合计
  - 样例前几行
- 导出成功后页面会显示结果反馈，并下载真实 `xlsx`

## 本地验证

运行测试：

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
```

检查服务就绪状态：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

前端测试与构建：

```bash
cd web
npm run test -- --run
npm run build
```

启动服务：

```bash
./scripts/start-backend.sh
```

启动前端：

```bash
./scripts/start-web.sh
```

访问：

- `GET /health`
- `GET /foundation/seed`
- `POST /imports/preview`
- `POST /imports/confirm`
- `POST /matching/run`
- `GET /matching/results`
- `GET /workbench`
- `GET /workbench/prototype`
- `POST /workbench/actions/confirm`
- `POST /workbench/actions/difference`
- `POST /workbench/actions/exception`
- `POST /workbench/actions/offline`
- `POST /workbench/actions/offset`
- `GET /integrations/oa`
- `POST /integrations/oa/sync`
- `GET /integrations/oa/sync-runs`
- `GET /ledgers`
- `GET /reminders`
- `GET /reconciliation/cases`
- `GET /projects`
- `POST /projects`
