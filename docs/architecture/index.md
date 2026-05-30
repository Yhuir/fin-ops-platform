# 架构文档索引

## 总览

- `../../ARCHITECTURE.md`：系统架构总览。
- `system-overview.md`：模块边界和主要数据流。
- `data-model.md`：核心领域实体和状态设计。

## 专题

- `oa-integration.md`：OA 页面壳体、登录复用、菜单权限和部署路径。
- `persistence-and-read-models.md`：当前持久化、read model、缓存失效和性能演进。
- `deployment.md`：部署形态、环境、反向代理和发布边界。
- `backend-refactor/README.md`：Python-first 后端架构重构文档入口。
- `backend-refactor/target-architecture.md`：Python-first 目标架构、组件边界和技术取舍。
- `backend-refactor/module-refactor-plan.md`：模块拆分、职责、验收顺序和测试门禁。
- `backend-refactor/runtime-call-chain.md`：静态调用链、动态运行时序和优化规则。
- `backend-refactor/read-model-and-external-services.md`：Read Model、Redis、RabbitMQ、PostgreSQL、OA Mongo 和对象存储契约。
- `backend-refactor/migration-roadmap.md`：分阶段重构路线、merge 策略和回滚口径。
- `backend-refactor/ai-execution-rules.md`：Codex/Gemini 执行 prompt 时必须遵守的状态、测试和分支规则。
- `backend-refactor/migration-state-log.md`：AI 状态机，记录 prompt 完成度、验证结果和下一步上下文。
- `backend-refactor/refactor-prompts.md`：经过审查的可执行 prompt 库。

## 历史资料

- 旧方案和阶段性计划已归档到 `../archive/legacy-docs/` 与 `../archive/superpowers/`。
