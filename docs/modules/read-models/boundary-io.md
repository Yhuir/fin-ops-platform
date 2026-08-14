# Read Model 退役边界与 I/O

日期：2026-08-15

## 模块状态

- 状态：retired；无运行时 public surface。
- 目标：防止旧 projection 链重新进入页面、API、worker、部署或监控。

## I/O

本模块没有输入和输出。页面读取的当前边界是：

```text
React page -> typed API client -> HTTP route -> page query service
           -> canonical repository -> PostgreSQL read-only snapshot
```

写入边界是 canonical service/UoW；必要的 OA sync、import、settings maintenance 和 Workbench matching
分别进入自己的 durable domain job，不产生页面刷新事件。

## 文件范围

已删除的服务、repository、worker、script 和 frontend barrier 不得重建。仅允许：

- 历史 migrations/checksum drift 记录；
- `0149_remove_read_model_runtime.sql` 的精确 drop；
- `retired_projection_event_audit.py` 与其他负向 contract guard；
- 本目录的退役说明。

## 依赖方向

- 页面/route/service -> narrow canonical repository。
- Worker -> 明确 domain service/repository。
- 禁止任何层依赖已退役模块、`read_model` schema、dirty scopes 或 refresh event。

## 删除与验证

- Migration 0149 只删除已知遗留对象，遇到未知 relation 会 fail closed。
- 当前 release 不提供旧 schema 的兼容 fallback；forward-only migration 后只允许向前修复。
- `tests/test_read_model_runtime_removal.py` 和 whole-repo scan 是机械防回归合同。
