# Prompt 07 OA Integration Foundation Design

## Goal

在现有银企核销系统之外建立独立的 `Integration Hub`，为未来真实 OA 接入提供稳定边界、主数据映射能力和同步轨迹，同时不让 OA 逻辑侵入核心核销服务。

## Scope

本次只覆盖以下内容：

- 独立的 OA 适配器接口
- `Mock OA` 适配器
- 客商、项目、审批单、付款申请、报销单的映射与同步模型
- 基础同步接口、最近同步结果、失败重试入口
- 当前原型页中的只读 `OA 同步` 视图

本次不做：

- 真实 OA 网络连接
- 定时调度器
- OA 单据直接进入三栏核销台
- OA 单据对核销动作的强校验

## Design

### 1. Boundary

新增 `services/integrations.py` 作为 `Integration Hub`：

- 上游只依赖 `OAAdapter`
- 下游只向外暴露同步结果、映射关系和读模型
- 核销服务不直接调用 OA 适配器

现有核心模块只接受“已经同步完成的主数据或外部引用”，而不是直接处理 OA 拉取逻辑。

### 2. Domain Objects

新增几类独立模型：

- `ProjectMaster`：项目主数据
- `OADocument`：审批单 / 付款申请 / 报销单的统一只读模型
- `IntegrationMapping`：`external_id -> internal_object_id` 映射
- `IntegrationSyncRun`：同步批次
- `IntegrationSyncIssue`：逐条失败原因

其中客商映射会优先尝试按规范化名称挂接现有导入形成的 `Counterparty`，只补充 `oa_external_id`，不改核销状态。

### 3. Sync Flow

同步流程统一为：

1. 用户触发某个 scope 的同步
2. `Integration Hub` 调用 `MockOAAdapter`
3. 校验并标准化外部记录
4. 写入映射、项目和单据读模型
5. 生成 `IntegrationSyncRun + IntegrationSyncIssue`
6. 记录审计日志

支持的 scope：

- `all`
- `counterparties`
- `projects`
- `approval_forms`
- `payment_requests`
- `expense_claims`

### 4. API

新增接口：

- `GET /integrations/oa`
- `POST /integrations/oa/sync`
- `GET /integrations/oa/sync-runs`
- `GET /integrations/oa/sync-runs/{run_id}`

`POST /integrations/oa/sync` 支持可选 `retry_run_id`，用于重新执行同 scope 同步。

### 5. Prototype

继续沿用现有原型页，只增加一个平行视图：

- 顶部入口 `OA 同步`
- 页面展示同步概览、scope 卡片、最近同步记录
- 只读展示映射到的客商、项目、OA 单据
- 提供 `同步全部` 与按 scope 重试入口

它不改变现有三栏核销台交互，也不自动弹出详情。

## Impact

### Backend

- `domain/enums.py`：增加集成来源、对象类型、同步状态枚举
- `domain/models.py`：增加 OA 同步与映射模型
- `services/imports.py`：暴露客商列表 / 查找能力供映射层使用
- `services/integrations.py`：新增 `Integration Hub`
- `app/server.py`：新增 OA 集成接口与健康检查能力

### Frontend Prototype

- `web/prototypes/reconciliation-workbench-v2.html`：增加只读 `OA 同步` 视图和同步按钮

## Testing

至少覆盖：

- 客商同步能映射已有 `Counterparty`
- 项目和 OA 单据可同步并查询
- 同步运行记录支持重试引用
- OA API round-trip
- 原型页脚本保持可解析
