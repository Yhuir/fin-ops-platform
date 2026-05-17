# Prompt 09：API 分批迁移到 Axum

```text
/goal
你是 Codex 子代理：API 迁移批次负责人。工作目录是 /Users/yu/Desktop/fin-ops-platform。

目标：
把现有 Python API 按模块和风险分批迁移到 Axum，保持低耦合和可回滚。不一次性重写全部后端。

必须读取：
- AGENTS.md
- docs/architecture/backend-refactor/migration-roadmap.md
- docs/architecture/backend-refactor/target-architecture.md
- docs/exec-plans/active/backend-refactor-inventory.md
- docs/dev/api-contracts.md
- web/src 相关 API client
- backend/src/fin_ops_platform/app/server.py

迁移顺序：
批次 1：低风险只读
- health。
- settings read。
- session/me 或权限上下文只读。
- app metadata。

批次 2：文件和导入元数据
- import history。
- file metadata。
- upload preflight。
- 不先迁移确认写入。

批次 3：工作台读
- 单月 read model 命中路径。
- 搜索 read model。
- 不先迁移 all-time 重查询。

批次 4：导入确认和撤回
- idempotency。
- audit。
- outbox。
- read model rebuild。

批次 5：核销和异常写操作
- confirm relation。
- revoke relation。
- exception create/resolve/revert。
- optimistic lock。

批次 6：高风险运维
- data reset。
- rebuild。
- destructive cleanup。
- 必须最后迁移。

每个批次必须拆成：
1. 契约冻结
   - 记录旧 API 请求/响应。
   - 前端调用点。
   - 错误码。

2. Axum route
   - route module。
   - request/response DTO。
   - auth context。

3. service/repository
   - service use case。
   - repository SQL。
   - transaction boundary。

4. 测试
   - unit tests。
   - integration tests。
   - contract fixture。

5. 影子验证
   - 旧 Python 和新 Axum 对比。
   - 差异报告。

禁止：
- 不在同一批次迁移多个高风险写模块。
- 不让 route 直接写 SQL。
- 不绕过审计和幂等。
- 不删除旧 Python API，直到切换和回滚方案完成。

交付物：
- docs/architecture/backend-refactor/api-migration-batches.md。
- 每批次独立实施 prompt 或 task list。
- 如果实现代码，每批次单独提交建议。

验收：
- 每个 API 有模块归属。
- 每个写 API 有事务、幂等、审计、outbox。
- 每批次可单独回滚。
- 前端调用契约不被无意破坏。
```

