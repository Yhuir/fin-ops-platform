# Prompt 04A：PostgreSQL 基础 Schema 与公共约束

```text
你是 Codex 子代理：PostgreSQL 基础 schema 负责人。

目标：
只实现 PostgreSQL 基础 schema、扩展、公共类型、审计基础和 migration 结构。不要一次性创建全部业务表。

必须读取：
- docs/architecture/backend-refactor/data-model-and-read-models.md
- docs/exec-plans/active/backend-refactor-prompts/04-postgresql-schema-and-migrations.md

范围：
- 建立 migration 目录。
- 创建 schema：app、read_model、job、audit、staging。
- 启用扩展：pgcrypto、pg_trgm、btree_gin。
- 建立公共枚举或 check 约束策略。
- 建立 audit.events 基础表。
- 建立 migration 版本说明文档。

不做：
- 不建银行流水、发票、OA、核销大表。
- 不建 read model 细表。
- 不实现 API。

交付物：
- 第一批基础 migration。
- docs/architecture/backend-refactor/postgresql-schema-notes.md 中的基础 schema 章节。

验收：
- 空库 migration 可执行。
- schema 和扩展存在。
- 公共约束命名清晰。
- 不引入业务耦合。
```

