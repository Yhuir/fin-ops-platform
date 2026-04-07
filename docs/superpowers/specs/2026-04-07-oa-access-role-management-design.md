# OA Access Role Management Design

日期：2026-04-07

## Goal

重构当前 `fin-ops-platform` 的 OA 权限模型，使其同时满足：

- 账户要么在 OA 中看得见且可访问此 app，要么完全看不见且无法访问
- 对于可访问账户，再区分：
  - `所有操作均可`
  - `只可看和只可导出`
- 只有 OA 账户 `YNSYLP005` 可以管理上述权限

## Problem with Current Model

当前模型过于单一：

- 只有一个“能不能访问”的口径
- 无法区分只读导出用户和全操作用户
- 关联台 `设置` 里的 `访问账户管理` 只能维护简单白名单
- 管理入口没有被限制为 `YNSYLP005`

这会带来三个问题：

1. 用户能访问后，默认具备全部写操作能力
2. 无法把领导/审计/查看人员限制成“只看和导出”
3. 无法明确谁能管理 app 内权限

## Target Permission Model

## Layer 1: Visibility and App Access

账户分成两类：

1. `visible_and_accessible`
   - 在 OA 中看得见 `财务运营平台`
   - 能打开页面
   - 能访问受保护 API
2. `hidden_and_denied`
   - 在 OA 中看不见入口
   - 直接访问 URL 也返回 `403`
   - API 也返回 `403`

## Layer 2: Operation Capability

对于 `visible_and_accessible` 的账户，再分成两类：

1. `full_access`
   - 所有读写操作都允许
2. `read_export_only`
   - 只允许查看、搜索、导出
   - 不允许任何会改变业务状态的操作

## Layer 3: Administration Capability

只有 `YNSYLP005` 属于管理员。

管理员能力包括：

- 维护 app 可访问账户
- 维护全操作 / 只读导出分组
- 查看和修改权限配置

第一阶段明确要求：

- 只有 `YNSYLP005` 能看到并使用 `访问账户管理`
- 其他全操作用户也不能修改权限

## Authorization Vocabulary

推荐把系统内部口径统一成 3 个能力位：

- `can_access_app`
- `can_mutate_data`
- `can_admin_access`

并把常见账户类型映射成：

| 账户类型 | can_access_app | can_mutate_data | can_admin_access |
| --- | --- | --- | --- |
| 不可见账户 | false | false | false |
| 只读导出账户 | true | false | false |
| 全操作账户 | true | true | false |
| 管理员 `YNSYLP005` | true | true | true |

## OA Integration Rules

## OA Menu Visibility

OA 菜单仍负责“看得见 / 看不见”。

因此：

- `can_access_app = true` 的账户，需要在 OA 菜单体系里可见
- `can_access_app = false` 的账户，需要在 OA 菜单体系里不可见

实现上可以继续保留 OA 权限：

- `finops:app:view`

但 app 自己还要有更细的运行时权限模型。

## Backend Enforcement

后端必须在每次请求中判断：

1. 当前用户是否 `can_access_app`
2. 当前请求是否属于写操作
3. 如果是写操作，当前用户是否 `can_mutate_data`
4. 如果是权限管理接口，当前用户是否 `can_admin_access`

返回口径：

- 无 OA 会话：`401`
- 无 app 访问资格：`403`
- 只有只读权限但发起写操作：`403`
- 非管理员访问权限管理接口：`403`

## Frontend Enforcement

前端不作为唯一安全边界，但需要把权限意图表达清楚。

## Session Bootstrap

`GET /api/session/me` 需要返回更完整的权限结构，例如：

- `allowed`
- `access_tier`
- `can_export`
- `can_mutate`
- `can_admin_access`

## UI Behavior

### Hidden/Denied Accounts

- 不展示 app 内容
- 直接显示 403 页面

### Read/Export Only Accounts

- 可查看：
  - 关联台
  - 税金抵扣
  - 成本统计
  - 搜索
  - 详情
- 可使用：
  - 导出
- 禁用：
  - 导入
  - 确认关联
  - 取消关联
  - 异常处理
  - 忽略 / 撤回忽略
  - 税金抵扣计划修改
  - 设置保存

### Full Access Accounts

- 允许现有全部业务操作
- 但不自动具备权限管理能力

### Administrator `YNSYLP005`

- 在 `设置` 中可见 `访问账户管理`
- 可以调整：
  - 可访问账户
  - 只读导出账户
  - 全操作账户

## Workbench Settings Redesign

当前 `访问账户管理` 需要从简单白名单改成结构化权限配置。

建议改成三个清晰分区：

1. `可访问账户`
   - 定义谁在 OA 中可见且可访问
2. `只读导出账户`
   - 属于可访问账户子集
3. `全操作账户`
   - 属于可访问账户子集

并增加一个管理员提示：

- 当前只有 `YNSYLP005` 可维护权限

第一阶段不在 UI 上开放“多管理员”，管理员固定为后端内置规则。

## Backend Data Model

当前 `app_settings` 中已有 `allowed_usernames`，需要扩展成：

- `allowed_usernames`
- `readonly_export_usernames`
- `admin_usernames`

其中：

- `readonly_export_usernames` 必须是 `allowed_usernames` 子集
- `admin_usernames` 第一阶段默认固定包含 `YNSYLP005`
- `admin_usernames` 也必须是 `allowed_usernames` 子集

## API Surface

至少需要补齐：

- `GET /api/settings/access-control`
- `POST /api/settings/access-control`

返回和保存结构应明确区分：

- 可访问
- 只读导出
- 管理员

## Write Operation Classification

系统里所有写操作都必须归类进“只读导出用户不可用”的集合。

至少包含：

- 导入
- workbench 动作
- 忽略 / 撤回忽略
- 异常处理 / 取消异常处理
- 税金抵扣计划勾选与计算提交
- 设置保存

导出与查看类接口保留可用。

## Acceptance Criteria

1. 无访问资格账户：
   - 在 OA 中看不见菜单
   - 直接访问 app 页面返回 `403`
   - 直接访问 API 返回 `403`
2. `只可看和只可导出` 账户：
   - 能查看页面和导出
   - 任意写操作返回 `403`
   - 前端写操作按钮禁用或隐藏
3. `所有操作均可` 账户：
   - 能执行业务读写操作
   - 但不能管理访问账户
4. `YNSYLP005`：
   - 可进入 `设置 -> 访问账户管理`
   - 可维护访问和操作权限
5. 权限保存后，前后端行为一致。
