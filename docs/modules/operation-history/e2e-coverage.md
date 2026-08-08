# 操作历史 E2E 覆盖

| Spec | 本地门禁 | 生产验证 |
| --- | --- | --- |
| `AUDIT-E2E-001` | API/route/frontend permission tests | 005 与非 005 smoke |
| `AUDIT-E2E-002` | service/API tests | 执行有界测试写并查询 request id |
| `AUDIT-E2E-003` | API failure-path tests | 只读核对失败事件 |
| `AUDIT-E2E-004` | PostgreSQL migration integration test | transaction rollback 内验证 trigger，不污染业务数据 |
