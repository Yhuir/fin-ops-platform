# 权限与审计测试入口

## 现金后端先行回归（2026-09-07）

- `tests/test_cash_permissions.py`：cash 二态授权/即时撤销、只有005管理权限、cash key 在既有 Settings 规范化往返中保留、未知层级拒绝、精确路由段、写请求不冒充只读、普通后台任务和全局 System Audit owner 排除现金。
- `tests/test_permissions_write_entry_inventory.py`：精确允许 cash 后端先行，所有旧前端/后端页面仍匹配；没有删除已有授权/退役字段/无缓存队列断言。
- 对应七类测试：业务权限规则、service、API/路由边界、全局读侧排除和旧功能回归适用；本轮不实现现金前端组件或新增 worker/cache，完整 HTTP 审计及现金业务链由现金入口测试负责。

## 七类测试适用性

| 类别 | 适用性 | 主要覆盖 |
| --- | --- | --- |
| 业务核心单元 | 适用 | page set 判定、005 固定管理员、非法/空/重复 page keys、provider fail closed |
| Service | 适用 | Settings CAS、OA user resolve、OA 两角色同步、audit、持久化失败补偿 |
| API contract | 适用 | session payload、ACL GET/PUT/user search、页面 API 403、admin-only 403 |
| Read model/cache/job | 不适用 | ACL 不新增 read model、cache、queue 或 worker；测试机械保证零新增 I/O |
| Frontend interaction | 适用 | 侧栏过滤、直达跳转、双栏账户/checkbox 编辑、409 草稿保留 |
| E2E business flow | 适用 | 005 搜索 OA 用户→勾选页面→保存→新 session 只看到授权页面 |
| Existing regression | 适用 | 全量 backend/frontend、页面主链路 E2E、settings/admin control plane |

## 验证命令

```bash
python3 -m pytest -q
cd web && npm test -- --run
cd web && npm run build
cd web && npx playwright test e2e/permissions-role-matrix.spec.ts
bash scripts/verify.sh lint
```

生产验证使用 `scripts/with-production-admin-token.sh` 包裹 access-control preflight 与只读 smoke，禁止打印 token。
