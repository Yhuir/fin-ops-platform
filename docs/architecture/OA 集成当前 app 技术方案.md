# OA 集成当前 app 技术方案

日期：2026-04-07

> 注：本文档现已升级到 `2026-04-07` 的权限分层口径。  
> 旧的“只有单一 `finops:app:view` 就够了”的方案，只能作为 OA 接入第一阶段的历史背景，不能再作为当前真实执行标准。

## 1. 目标

将当前 `fin-ops-platform` 作为一个受控财务子系统接入现有 OA：

- 在 OA 页面体系下打开，不单独暴露一套登录页
- 直接复用 OA 现有登录态
- 只对少数有权限账户可见
- 未授权用户即使手工输入地址，也不能访问页面和 API

本方案基于真实 OA 源码分析得出，不是抽象推测：

- OA 前端：`/Users/yu/Desktop/sy/smart-oa-ui`
- OA 后端：`/Users/yu/Desktop/sy/smart_oa`

## 2. 结论

这个功能可行，而且可行性高。

原因有三个：

1. OA 已经有现成登录体系  
   OA 前端使用 `Admin-Token` cookie 保存 token，并通过 `Authorization: Bearer ...` 调接口。

2. OA 已经有现成用户信息与权限体系  
   当前用户信息通过 `/system/user/getInfo` 获取；菜单通过 `/system/menu/getRouters` 动态下发。

3. OA 前端已经支持“内链 iframe 页面”  
   可直接把你现在的 app 作为一个页面嵌入 OA，不需要先把 React 重写成 Vue 子页面。

## 3. 真实代码依据

### 3.1 OA 登录态

OA 前端 token 存储位置：

- `/Users/yu/Desktop/sy/smart-oa-ui/src/utils/auth.js`

关键点：

- cookie key：`Admin-Token`
- token 不是 HttpOnly，由前端 JS 可读

OA 请求自动带 token：

- `/Users/yu/Desktop/sy/smart-oa-ui/src/utils/request.js`

关键点：

- 每次请求自动加 `Authorization: Bearer ${token}`

### 3.2 OA 当前用户与权限

OA 前端获取当前用户信息：

- `/Users/yu/Desktop/sy/smart-oa-ui/src/api/login.js`

接口：

- `GET /system/user/getInfo`

OA 后端返回当前用户、角色、权限：

- `/Users/yu/Desktop/sy/smart_oa/smart-oa-modules/smart-oa-system/src/main/java/com/jovefast/system/controller/SysUserController.java`

返回内容包括：

- `user`
- `roles`
- `permissions`

### 3.3 OA 动态菜单

OA 前端动态菜单来源：

- `/Users/yu/Desktop/sy/smart-oa-ui/src/api/menu.js`
- `/Users/yu/Desktop/sy/smart-oa-ui/src/store/modules/permission.js`

接口：

- `GET /system/menu/getRouters`

OA 后端菜单接口：

- `/Users/yu/Desktop/sy/smart_oa/smart-oa-modules/smart-oa-system/src/main/java/com/jovefast/system/controller/SysMenuController.java`

### 3.4 OA 已支持 iframe 内链

OA 内链 iframe 组件：

- `/Users/yu/Desktop/sy/smart-oa-ui/src/layout/components/InnerLink/index.vue`

菜单服务对 http(s) 地址会生成 `InnerLink` 组件：

- `/Users/yu/Desktop/sy/smart_oa/smart-oa-modules/smart-oa-system/src/main/java/com/jovefast/system/service/impl/SysMenuServiceImpl.java`

这意味着：

- 可以直接在 OA 菜单里新增一个“财务运营平台”入口
- 入口指向部署后的 `fin-ops-platform` 页面地址
- OA 内部会以 iframe 方式承载

### 3.5 OA 网关已做 token 校验

OA gateway 鉴权过滤器：

- `/Users/yu/Desktop/sy/smart_oa/smart-oa-gateway/src/main/java/com/jovefast/gateway/filter/AuthFilter.java`

关键点：

- 校验 `Authorization`
- 解析 JWT
- 查 Redis 会话
- 向下游注入：
  - 用户 ID
  - 用户名
  - user key

这说明 OA 已有完整的统一鉴权链。

## 4. 推荐集成架构

推荐采用：

- `OA 菜单 + iframe 页面承载`
- `fin-ops-platform 独立前后端继续部署`
- `与 OA 同域部署`
- `app 后端复用 OA token 识别当前用户`
- `权限同时在 OA 菜单层和 app 后端层生效`

### 4.1 为什么不建议直接塞进 OA 前端代码里

不建议把当前 React app 直接重写进 OA Vue 前端，原因是：

- 当前 app 规模已经不小
- React 页面、状态和 API 契约已独立成型
- 强行迁入 OA 前端会显著增加重构成本
- 后续迭代会和 OA 主系统发布周期强耦合

因此第一阶段最稳的方式是：

- 逻辑独立
- 登录复用
- 页面挂载到 OA 菜单里

## 5. 目标部署形态

推荐部署路径：

- OA 主系统：`https://oa.company.com/`
- fin-ops 前端：`https://oa.company.com/fin-ops/`
- fin-ops 后端：`https://oa.company.com/fin-ops-api/`

然后在 OA 菜单里配置一个内链地址，例如：

- `https://oa.company.com/fin-ops/`

这样具备几个优势：

- 同域，cookie 可直接共享
- iframe 无跨域限制问题
- token 读取更简单
- 部署和运维边界仍然清楚

## 6. 登录复用方案

## 方案选择

本方案推荐：

- 前端复用 OA 的 `Admin-Token`
- 后端不自己发 token
- 后端通过 OA token 获取当前用户并校验权限

### 6.1 前端

`fin-ops-platform` 前端新增一层 OA 会话适配：

- 从 cookie 读取 `Admin-Token`
- 所有 API 请求自动加：
  - `Authorization: Bearer ${token}`

当前 app 不再显示自己的登录页。

### 6.2 后端

Python 后端新增鉴权中间层：

1. 从请求头读取 `Authorization`
2. 使用该 token 请求 OA 的：
   - `/system/user/getInfo`
3. 获取：
   - 当前用户
   - 角色
   - 权限
4. 判断是否有访问 `fin-ops-platform` 的权限
5. 无权限时返回 `403`

### 6.3 为什么后端不能只信前端

不能只在前端判断“这个用户看不看得见”，因为那样用户手工输入 API 地址仍然能访问数据。

所以必须：

- 前端隐藏
- 后端强制拦截

## 7. 可见性与权限模型

你的需求是：

- 只有少数账户可见
- 其他账户完全不可见

推荐权限模型：

### 7.1 两层权限模型

接入 OA 后，权限不再只有“能不能进”这一层，而是拆成两层：

1. **可见性 / 访问层**
   - `在 OA 系统看得见并可访问此 app`
   - `在 OA 系统看不见且访问不了此 app`
2. **操作能力层**
   - `所有操作均可`
   - `只可看和只可导出`

### 7.2 OA 侧可见性

OA 菜单层仍然负责“看得见 / 看不见”：

- 有访问权限的账户：看得见菜单，并能进入 app
- 无访问权限的账户：在 OA 中看不见菜单

建议继续保留一个菜单可见性权限，例如：

- `finops:app:view`

并新增菜单：

- 名称：`财务运营平台`
- 归属：建议挂在 `财务管理`
- 类型：菜单
- 路径：部署后的 `https://oa.company.com/fin-ops/`
- 组件：由 OA 内链逻辑处理
- 权限标识：`finops:app:view`

### 7.3 app 后端二次校验

`fin-ops-platform` 后端对每个 API 继续校验两件事：

1. 当前用户是否具备 app 访问资格
2. 当前用户属于哪种操作能力等级

也就是说：

- 无 app 访问资格：
  - 页面 `403`
  - API `403`
- 有 app 访问资格，但只有 `只可看和只可导出`：
  - 允许查看、搜索、导出
  - 禁止导入、确认关联、异常处理、忽略、设置修改等写操作

### 7.4 推荐权限结构

推荐把后端实际判断口径整理成：

- `finops:app:view`
  - 负责 OA 菜单可见性与基础访问资格
- `finops:app:operate`
  - 负责是否拥有“所有操作均可”
- `finops:app:admin`
  - 负责是否可管理访问账户与权限模型

如果 OA 现阶段不方便一次性加全三种权限，也可以采用：

- OA 只保留 `finops:app:view`
- app 自己维护：
  - `allowed_usernames`
  - `readonly_export_usernames`
  - `admin_usernames`

当前正式执行标准最少要确保：

- `YNSYLP005` 是唯一管理员
- 只读用户不能触发任何写操作
- 非白名单用户看不见且进不来
- OA 菜单可见性必须和 `allowed_usernames` 同步

### 7.5 `YNSYLP005` 的特殊角色

当前业务要求里，只有 OA 账户 `YNSYLP005` 可以管理以下内容：

- 哪些账户可访问此 app
- 这些可访问账户属于：
  - `所有操作均可`
  - `只可看和只可导出`

因此，`YNSYLP005` 在系统中需要被视为唯一初始管理员，而且是当前唯一允许管理权限的账户。

建议：

- OA 侧给 `YNSYLP005` 分配最高级别 app 权限
- app 后端再额外校验 `YNSYLP005` 或管理员名单
- 关联台 `设置` 中只有管理员能看到“访问账户管理”

### 7.6 设置页中的账户管理能力

关联台 `设置` 应新增/重构为：

- `可访问账户`
  - 这些账户在 OA 中看得见并可访问此 app
- `只读导出账户`
  - 这些账户属于“只可看和只可导出”
- `全操作账户`
  - 这些账户属于“所有操作均可”
- `管理员账户`
  - 第一阶段固定仅 `YNSYLP005`

后端保存后，真实环境必须同步两个方向：

1. app 自己的访问控制数据
2. OA 菜单可见性所依赖的角色/权限绑定

建议把 OA 侧角色固定成三类：

- `finops_read_export`
- `finops_full_access`
- `finops_admin`

同步规则：

- `allowed_usernames` 之外的账户：
  - 从 OA 这三类角色全部移除
- `readonly_export_usernames`：
  - 绑定到 `finops_read_export`
- 全操作账户：
  - 绑定到 `finops_full_access`
- `YNSYLP005`：
  - 绑定到 `finops_admin`

### 7.4 需要保护的范围

必须全部拦住，不只工作台：

- 关联台
- 搜索
- 税金抵扣
- 成本统计
- 导出
- 设置
- 导入
- 任意 `/api/*`

## 8. 页面集成方案

## 第一阶段推荐做法

### OA 页面侧

在 OA 里新增一个菜单入口，使用现有 `InnerLink` 承载当前 app。

优点：

- 实现快
- 不需要改动 OA 主壳体结构
- 发布风险低
- 登录态天然复用

### fin-ops 页面侧

你的 app 需要增加：

- `session / me` 初始化接口
- 未授权页 `403`
- 无 token / token 失效页
- “当前用户”上下文

## 9. 后端改造点

`fin-ops-platform` 后端需要新增一层 OA 安全适配：

### 9.1 新增能力

- 读取 Bearer token
- 获取 OA 当前用户信息
- 解析 roles / permissions
- 请求级缓存或短 TTL 缓存
- 统一鉴权失败返回

### 9.2 建议新增接口

- `GET /api/session/me`

返回：

- 当前用户名
- 显示名
- 角色
- 权限
- `allowed = true/false`

作用：

- 前端初始化页面时确认当前会话是否可访问本系统

### 9.3 建议新增模块

- `backend/src/fin_ops_platform/services/oa_identity_service.py`
- `backend/src/fin_ops_platform/services/access_control_service.py`
- `backend/src/fin_ops_platform/app/auth.py`

### 9.4 建议环境变量

- `FIN_OPS_OA_BASE_URL`
- `FIN_OPS_OA_USER_INFO_PATH`
- `FIN_OPS_OA_PASSWORD_VERIFY_PATH`
- `FIN_OPS_OA_REQUIRED_PERMISSION`
- `FIN_OPS_OA_SESSION_CACHE_TTL_SECONDS`

默认：

- `FIN_OPS_OA_USER_INFO_PATH=/system/user/getInfo`
- `FIN_OPS_OA_PASSWORD_VERIFY_PATH=/system/user/profile/updatePwd`
- `FIN_OPS_OA_REQUIRED_PERMISSION=finops:app:view`

## 10. 前端改造点

`fin-ops-platform` 前端需要新增：

- 统一 token 读取
- `session/me` 启动检查
- 未授权页
- 会话过期处理

### 10.1 不再需要的能力

- 不做自己的登录页
- 不维护自己的用户名密码体系

### 10.2 需要新增的能力

- `web/src/features/session/api.ts`
- `web/src/contexts/SessionContext.tsx`
- `web/src/components/auth/ForbiddenPage.tsx`
- `web/src/components/auth/SessionGate.tsx`

## 11. OA 侧需要改的点

需要改两处仓库：

### 11.1 `smart-oa-ui`

- 新增菜单入口可见性验证
- 菜单配置挂到现有导航里
- 如需要，优化 iframe 页面高度、自适应和关闭策略

### 11.2 `smart_oa`

- 新增菜单权限项 `finops:app:view`
- 给特定角色/用户授权
- 如部署需要，可补一个更轻量的“当前用户信息”接口给 app 调用

说明：

当前严格来说，`/system/user/getInfo` 已够用，不一定必须再写新接口。

## 12. 风险与控制点

### 风险 1：不同域部署

如果 app 和 OA 不同域：

- token 共享会复杂
- iframe 会遇到跨域约束
- 会话判断和导出都更麻烦

控制建议：

- 必须优先争取同域部署

### 风险 2：只做菜单隐藏，不做后端校验

这会导致：

- 用户手工访问 URL 仍能看到系统

控制建议：

- 后端所有 API 做强制鉴权

### 风险 3：Python 后端完全依赖前端传用户名

这会导致：

- 身份可伪造

控制建议：

- 后端只信 OA token 校验结果，不信前端自报身份

## 13. 推荐实施顺序

1. 给 `fin-ops-platform` 增加 OA token 鉴权与 `session/me`
2. 在 app 后端加权限校验和 `403`
3. 在 OA 新增菜单与权限码 `finops:app:view`
4. 把 app 以前端子路径方式部署到 OA 域名下
5. 联调 iframe、高度、自适应和登出失效
6. 做全链路验收

## 14. 验收标准

以下全部满足才算完成：

1. OA 登录后，无需再次登录即可打开当前 app
2. 有权限账户能在 OA 菜单中看到入口
3. 无权限账户在 OA 菜单中完全看不到入口
4. 无权限账户直接访问 app URL 时返回 `403`
5. 所有 `/api/*` 都有权限保护
6. 登出 OA 后，再访问 app 会失效
7. 关联台、税金抵扣、成本统计、导出均在授权链路下正常工作
8. 只读导出用户无法执行任何写操作
9. 只有 `YNSYLP005` 能管理访问账户权限
10. app 配置与 OA 菜单可见性同步后，不出现“看得见但进不去”或“进得去但看不见菜单”的不一致

## 15. 对应实施文档

- 设计文档：[/Users/yu/Desktop/fin-ops-platform/docs/superpowers/specs/2026-04-03-oa-shell-auth-visibility-design.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/specs/2026-04-03-oa-shell-auth-visibility-design.md)
- 实施计划：[/Users/yu/Desktop/fin-ops-platform/docs/superpowers/plans/2026-04-03-oa-shell-auth-visibility.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/plans/2026-04-03-oa-shell-auth-visibility.md)
- Prompt 28：[/Users/yu/Desktop/fin-ops-platform/prompts/28-oa-shell-auth-foundation.md](/Users/yu/Desktop/fin-ops-platform/prompts/28-oa-shell-auth-foundation.md)
- Prompt 29：[/Users/yu/Desktop/fin-ops-platform/prompts/29-oa-menu-iframe-integration.md](/Users/yu/Desktop/fin-ops-platform/prompts/29-oa-menu-iframe-integration.md)
- Prompt 30：[/Users/yu/Desktop/fin-ops-platform/prompts/30-oa-visibility-and-access-control.md](/Users/yu/Desktop/fin-ops-platform/prompts/30-oa-visibility-and-access-control.md)
- Prompt 31：[/Users/yu/Desktop/fin-ops-platform/prompts/31-oa-integration-deployment-and-qa.md](/Users/yu/Desktop/fin-ops-platform/prompts/31-oa-integration-deployment-and-qa.md)
- 部署与回滚说明：[/Users/yu/Desktop/fin-ops-platform/deploy/oa/README.md](/Users/yu/Desktop/fin-ops-platform/deploy/oa/README.md)
- Nginx 示例：[/Users/yu/Desktop/fin-ops-platform/deploy/oa/nginx.fin-ops.conf.example](/Users/yu/Desktop/fin-ops-platform/deploy/oa/nginx.fin-ops.conf.example)
- 环境变量模板：[/Users/yu/Desktop/fin-ops-platform/deploy/oa/fin_ops.env.example](/Users/yu/Desktop/fin-ops-platform/deploy/oa/fin_ops.env.example)
- 菜单 SQL 模板：[/Users/yu/Desktop/fin-ops-platform/deploy/oa/fin_ops_menu.mysql.sql](/Users/yu/Desktop/fin-ops-platform/deploy/oa/fin_ops_menu.mysql.sql)
- 角色绑定 SQL 模板：[/Users/yu/Desktop/fin-ops-platform/deploy/oa/fin_ops_role_binding.mysql.sql](/Users/yu/Desktop/fin-ops-platform/deploy/oa/fin_ops_role_binding.mysql.sql)
- 用户角色同步 SQL 模板：[/Users/yu/Desktop/fin-ops-platform/deploy/oa/fin_ops_user_role_sync.mysql.sql](/Users/yu/Desktop/fin-ops-platform/deploy/oa/fin_ops_user_role_sync.mysql.sql)

## 16. Prompt 31 已落地内容

- 明确正式部署路径：
  - `/fin-ops/`
  - `/fin-ops-api/`
- 新增 OA 同域部署说明、环境变量模板和 Nginx 示例
- 补齐 OA token 复用链路说明：
  - `Admin-Token` -> `Authorization` -> `/api/session/me` -> OA `/system/user/getInfo`
- 补齐发布顺序、联调验收清单和回滚方案
- 补齐关键验证口径：
  - 登录复用
  - 菜单可见性
  - 403 拦截
  - workbench / tax / cost / export / search 可用性
