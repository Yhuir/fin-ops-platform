# 权限与审计测试入口

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
