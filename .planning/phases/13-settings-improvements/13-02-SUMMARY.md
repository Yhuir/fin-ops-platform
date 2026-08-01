---
phase: 13-settings-improvements
plan: "02"
status: complete
completed: 2026-08-02
requirements:
  - PAGE-15
  - PAGE-04
  - PAR-01
  - PAR-02
  - PAR-03
---

# 13-02 执行摘要

## 完成结果

- 普通 settings GET/POST 已与 ACL 完全分离；旧 ACL key 被明确拒绝，普通 full-access 用户仍可保存非权限设置且不会触发 OA。
- 新增 admin-only `GET/PUT /api/workbench/settings/access-control`：唯一管理员固定为 `YNSYLP005`，请求只能管理其他账号的 `full_access` / `read_export_only`，并以 `expected_version` 做 CAS。
- request ID 由 WSGI adapter 生成并覆盖客户端输入，同一 ID 贯穿 response 与 durable audit；actor 只来自可信 session。
- 权限判断改为一次 normalized ACL snapshot；删除 dynamic admin provider、环境变量管理员、local auth clone、三个 legacy username getter 与 pending-invoice generic replay。
- ACL 真变化才执行带 connect/read/write timeout 的 OA 同步；no-op、generic settings save 零 OA；known rollback 在锁内补偿，commit lost-ACK 通过 fresh-lock mutation proof 收敛。
- 未新增依赖、表、worker、outbox、cache 或通用事务框架。

## 验证

- affected backend suites：573 tests passed，5 个既有可选外部集成测试 skipped。
- `bash scripts/verify.sh backend`：3799 tests passed，52 个既有可选外部集成测试 skipped。
- 一次性本地 PostgreSQL `fin_ops_acl_test` 执行 `bash scripts/verify.sh settings-acl-postgres`：真实 server COMMIT + client lost-ACK recovery 测试通过；测试库已删除。
- 无 `FIN_OPS_TEST_DATABASE_URL` 时同一专用 gate exit 2，证明不会以 skip 伪绿。
- `bash scripts/verify.sh lint` 与 `git diff --check`：通过。

## 旧链路删除

- runtime 不再读取 `FIN_OPS_ADMIN_USERNAMES`，不再允许动态来源产生第二管理员。
- generic settings response、writer 与 service signature 不再承载 ACL。
- 测试管理员身份统一为 `YNSYLP005`；其他 full/read 测试账号通过专用 ACL command 配置，不保留测试专用 bypass。

## 后续

- Wave 2 将迁移 Web 设置弹窗到专用 ACL API，删除前端 legacy access-control mapping，并补 direct API 提权 E2E。
