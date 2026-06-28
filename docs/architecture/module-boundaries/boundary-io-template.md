# 模块边界与 I/O 模板

复制本模板到 `docs/modules/<module>/boundary-io.md`。当前每个登记模块都必须维护独立 `boundary-io.md`；模块 README 只保留入口和快速定位，不替代边界/I/O 合同。

## 模块身份

- Module key:
- 名称:
- 类型: 页面模块 / 资源模块 / API 模块 / Worker 模块 / 运维模块
- Route 或入口:
- Owner 文档:
- 相关产品文档:
- 相关架构文档:

## 职责边界

### 负责

- 

### 不负责

- 

### 禁止绕过

- 

## 输入 I/O

| 输入 | 来源 | 合同 | 校验点 |
| --- | --- | --- | --- |
| HTTP/API 入参 |  |  |  |
| Service 入参 |  |  |  |
| Repository 查询条件 |  |  |  |
| Direct query / legacy guard scope |  |  |  |
| Worker event |  |  |  |
| 前端用户操作/页面状态 |  |  |  |

## 输出 I/O

| 输出 | 目标 | 合同 | 一致性要求 |
| --- | --- | --- | --- |
| API 响应 |  |  |  |
| Direct payload / legacy guard |  |  |  |
| Affected scope / outbox event |  |  |  |
| Audit record |  |  |  |
| Worker job/result |  |  |  |
| 前端刷新信号 |  |  |  |

## 持久化与投影

- Owned tables:
- Legacy projection:
- Affected scope / outbox:
- Worker:
- Cache:
- External systems:

## 文件范围

| 层 | 文件或目录 | 说明 |
| --- | --- | --- |
| Backend route |  |  |
| Backend service |  |  |
| Repository / SQL |  |  |
| Worker / job |  |  |
| Frontend page |  |  |
| Frontend feature/API |  |  |
| Tests |  |  |
| Scripts / ops |  |  |

## 依赖方向

- 允许依赖:
- 必须通过的 gateway/facade:
- 禁止依赖:
- 删除旧链路条件:

## 测试与验证

| 类别 | 是否适用 | 入口 |
| --- | --- | --- |
| 业务核心单元测试 |  |  |
| Service 层测试 |  |  |
| API 合同测试 |  |  |
| Direct query/cache/worker/legacy guard 测试 |  |  |
| 前端组件与交互测试 |  |  |
| 端到端业务流集成测试 |  |  |
| 既有功能回归测试 |  |  |

## 生产验证

- 发布入口:
- Direct payload / affected scope 检查:
- 可控写操作样本:
- 回滚方式:
- 已知风险:

## 维护记录

| 日期 | 变更 | 验证 |
| --- | --- | --- |
|  |  |  |
