# Prompt 09A：低风险只读 API 迁移

```text
你是 Codex 子代理：低风险只读 API 迁移负责人。

目标：
只迁移健康检查、设置读取、session/me、app metadata 等低风险读 API 到 Axum。建立 API 迁移模板，不碰导入确认、核销写入、数据重置。

必须读取：
- docs/exec-plans/active/backend-refactor-prompts/05-axum-api-foundation.md
- docs/exec-plans/active/backend-refactor-inventory.md
- docs/dev/api-contracts.md
- web/src 相关 API client

范围：
- health/ready/metrics。
- settings read。
- session/me 或权限上下文只读。
- app metadata/version。

要求：
- 冻结请求/响应契约。
- route -> service -> repository 分层。
- 错误响应统一。
- 测试覆盖契约 fixture。

交付物：
- Axum routes。
- docs/architecture/backend-refactor/api-migration-batches.md 的批次 1。

验收：
- cargo test/check 通过。
- 不影响 Python 后端。
- 前端契约不破坏。
```

