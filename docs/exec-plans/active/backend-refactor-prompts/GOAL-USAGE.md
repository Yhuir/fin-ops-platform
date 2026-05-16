# 使用 `/goal` 执行 Prompt 的方式

## 推荐方式：执行完整续作总控

在 Codex 输入：

```text
/goal
请按下面 prompt 执行，不要从零重复安装 PostgreSQL 或重复备份 app Mongo。先读取当前状态，再拆分子代理执行。

粘贴 docs/exec-plans/active/backend-refactor-prompts/00-goal-master-current-state.md 的完整内容。
```

如果 Codex 支持直接引用文件，也可以写：

```text
/goal
使用 /Users/yu/Desktop/fin-ops-platform/docs/exec-plans/active/backend-refactor-prompts/00-goal-master-current-state.md 作为总控 prompt 执行。
先读取该文件和它引用的当前状态文档；不要重复执行已完成的 PostgreSQL 安装、app Mongo 备份和 0001-0007 migration 生成。
```

## 执行单个模块

适合一次只做一个模块，例如只做 app Mongo 导出工具：

```text
/goal
执行 /Users/yu/Desktop/fin-ops-platform/docs/exec-plans/active/backend-refactor-prompts/06a-mongo-export-tooling.md。
执行前必须读取 00-current-state-and-gates.md 和 backend-refactor-progress.md。
只实现 app Mongo 只读导出工具，不访问 OA 源数据库，不写 secret，不做生产切流。
```

## 当前最推荐的下一组 `/goal`

按顺序执行：

```text
/goal
执行 /Users/yu/Desktop/fin-ops-platform/docs/exec-plans/active/backend-refactor-prompts/06a-mongo-export-tooling.md。
执行前读取 00-current-state-and-gates.md。只做 app Mongo 规范化导出工具和导出 runbook，不访问 OA 源库。
```

```text
/goal
执行 /Users/yu/Desktop/fin-ops-platform/docs/exec-plans/active/backend-refactor-prompts/06b-postgres-import-validation-tooling.md。
执行前读取 00-current-state-and-gates.md。只做 PostgreSQL staging 导入和对账工具，不把数据直接写正式事实表。
```

```text
/goal
执行 /Users/yu/Desktop/fin-ops-platform/docs/exec-plans/active/backend-refactor-prompts/06c-data-migration-dry-run.md。
执行前读取 00-current-state-and-gates.md。只做 dry-run 和报告，不切换生产 API，不冻结 app Mongo。
```

## 必须附加的安全提示

每次 `/goal` 建议都附加这段：

```text
硬性约束：
1. 不备份、不导出、不恢复、不修改、不压测、不人工查询 OA 源数据库。
2. 不写入真实 secret、URI、密码、token。
3. PostgreSQL 不开放公网。
4. 不覆盖已有 app Mongo 备份。
5. 没有 dry-run 对账报告，不迁移生产数据。
6. 没有用户明确授权，不做生产切流。
```

## 如何判断一个 prompt 是否过大

如果一次 `/goal` 需要同时改这些内容，应拆分：

- 同时改导出工具、导入工具、API 和 Worker。
- 同时碰 Python 后端、Rust Axum、SQL migration 和服务器配置。
- 同时写多个高风险 API。
- 需要真实生产数据迁移。

拆分原则：

- 一个 prompt 只负责一个数据流或一个 API 批次。
- 每个 prompt 必须有独立验收。
- 每个 prompt 必须能失败后安全重试。
