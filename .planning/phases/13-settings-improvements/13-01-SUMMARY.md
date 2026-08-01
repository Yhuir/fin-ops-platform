---
phase: 13-settings-improvements
plan: "01"
status: complete
completed: 2026-08-02
requirements:
  - PAGE-15
  - PAGE-04
  - PAR-01
  - PAR-03
commits:
  - 67b2ace65
  - c41fa9b15
---

# 13-01 执行摘要

## 完成结果

- 新增 0132 migration：清理历史非法管理员、固定唯一管理员 `YNSYLP005`、对齐 formal/raw payload、初始化 ACL version，并用 validated CHECK 阻断旧 binary 再次写入非法管理员。
- generic settings writer 共享 ACL advisory lock，只合并非 ACL family；旧 payload 无法覆盖 ACL 或 version。
- 新增窄 ACL critical-section：锁内 snapshot、expected_version/CAS、settings + audit 同事务 commit、lost-ACK outcome unknown 与 fresh-lock mutation recovery。
- local state store 使用既有 `RLock` 提供等价 CAS 和 mutation proof；未新增表、依赖、worker、cache 或 outbox。

## 验证

- `PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_migrations.py tests/test_postgres_repositories_boundaries.py tests/test_state_store_contract.py tests/test_postgres_state_store.py -q`：152 passed。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations -v`：73 passed。
- `bash scripts/verify.sh lint`：通过。
- `git diff --check`：通过。

## 设计偏差与理由

- top-level generic/ACL writer 使用同一 session advisory lock；已有 caller-owned transaction 无法安全提前释放 session lock，因此使用相同 key 的 transaction advisory lock，由 PostgreSQL 在事务结束时释放。两种锁互相冲突，保持并发隔离且不引入通用 UoW。

## 后续

- Wave 1 将把 HTTP API、权限服务、动态鉴权和 OA 同步接到该窄端口，并删除 generic settings 的 ACL 输入/输出。
