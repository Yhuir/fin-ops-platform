# 页面访问权限 E2E 合同

权限事实源是 PostgreSQL `app.app_settings.page_access_accounts`。OA identity 只提供用户身份；前端侧栏和路由只做体验层投影，后端 `route_access_policy.py` 必须再次按页面 key 校验。

## 核心场景

| Spec ID | 场景 | 验收标准 |
| --- | --- | --- |
| `PERM-E2E-001` | 无页面账号 | `/api/session/me` 返回空 `allowed_page_keys` 和 `allowed=false`；业务页面不挂载，protected page API 403。 |
| `PERM-E2E-002` | 单页账号 | 侧栏只显示被授权页面；直达其他页面跳转到首个可访问页面；后端其他页面 API 403。 |
| `PERM-E2E-003` | 多页账号 | 每个勾选页面均可进入，并保留该页面原有业务读写/导出能力；不存在账号级操作层级。 |
| `PERM-E2E-004` | 固定管理员 | 只有 `YNSYLP005` 可见并调用访问账户、OA 凭据、数据重置和操作历史 control plane。 |
| `PERM-E2E-005` | OA 账户管理 | 005 从 OA 搜索账号/姓名，新增、删除、勾选页面并通过 versioned PUT 保存；响应回显 OA 名称与状态。 |
| `PERM-E2E-006` | 即时撤权 | 从 ACL 删除账号或其全部页面后，下一次 session/API 决策立即 denied，不依赖 OA role 或本地 cache。 |
| `PERM-E2E-007` | 未登记路由 | 受保护 API 没有页面映射时 fail closed；新增页面必须同步前后端 registry 与测试。 |

## 非账户权限门禁

系统健康状态仍可阻断写操作；这是运行安全边界，不是账户权限层级。业务状态、版本冲突、二次确认和数据重置密码复核也保持各自模块合同。
