# OA 集成底座说明

本文档对应 Prompt 07，说明当前 `Integration Hub` 的边界、已落地接口以及未来替换真实 OA 的最小改动点。

## 1. 当前实现范围

当前已经落地：

- 独立 `Integration Hub` 服务
- `Mock OA` 适配器
- 客商 / 项目 / OA 单据映射
- 同步批次与失败重试入口
- 原型页只读 `OA 同步` 视图

当前接口：

- `GET /integrations/oa`
- `POST /integrations/oa/sync`
- `GET /integrations/oa/sync-runs`
- `GET /integrations/oa/sync-runs/{run_id}`

## 2. 集成边界

OA 接入不直接侵入：

- 导入标准化
- 自动匹配引擎
- 人工核销服务
- 台账与提醒服务

它只做两件事：

1. 拉取外部主数据与单据
2. 维护 `external_id -> internal_object_id` 的映射关系

因此，未来接真实 OA 时，核心核销服务不需要因为“接入方式变化”而重构。

## 3. 当前支持的同步范围

- `all`
- `counterparties`
- `projects`
- `approval_forms`
- `payment_requests`
- `expense_claims`

说明：

- `counterparties` 会尝试按规范化名称匹配已有 `Counterparty`
- 若匹配成功，会补充 `oa_external_id`
- `projects` 与 `documents` 当前作为只读主数据保存在集成层

## 4. 当前模型

已新增：

- `ProjectMaster`
- `OADocument`
- `IntegrationMapping`
- `IntegrationSyncRun`
- `IntegrationSyncIssue`

关键字段：

- `IntegrationMapping.external_id`
- `IntegrationMapping.internal_object_type`
- `IntegrationMapping.internal_object_id`
- `IntegrationSyncRun.retry_of_run_id`

## 5. 原型页口径

`/workbench/prototype` 已新增 `OA 同步` 入口：

- 只读查看同步结果
- 可执行 `同步全部`
- 可按 scope 单独同步
- 可对最近同步记录执行 `重试`
- 点击 `详情` 统一走右侧详情抽屉

它不会把 OA 单据直接塞进三栏核销主表。

## 6. 真实 OA 替换点

未来接真实 OA 时，最小改动点是：

1. 保留 `IntegrationHubService`
2. 用真实适配器替换 `MockOAAdapter`
3. 在真实适配器里实现：
   - `fetch_counterparties()`
   - `fetch_projects()`
   - `fetch_documents(scope)`

也就是说，服务层和 API 层可以继续复用；主要变化集中在适配器实现和认证配置。

## 7. 验证方式

只跑 Prompt 07 相关测试：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_integration_service tests.test_integration_api tests.test_app -v
```

全量回归：

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
```
