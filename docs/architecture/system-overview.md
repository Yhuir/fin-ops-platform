# 系统边界与模块关系

## 系统边界

`fin-ops-platform` 是独立财务子系统，接入 OA 页面和登录态，但不并入 OA 前端或 OA 后端代码库。

```text
OA 页面 / 菜单 / 登录态
        |
        v
React 财务运营前端
        |
        v
Python 财务运营后端
        |
        +--> PostgreSQL：业务事实、设置、队列、审计和 SQL/read model
        +--> MinIO/S3：上传文件和已迁移附件对象
        +--> Redis：短 TTL cache、pub/sub wakeup、辅助锁
        +--> OA Mongo：仅独立 worker 只读同步到 PostgreSQL projection
        +--> 本地兼容存储：开发或历史迁移路径
```

## 后端模块

- `app/`：HTTP 路由、鉴权、响应组装、跨服务协调。
- `domain/`：领域模型和枚举。
- `services/`：导入、匹配、工作台、核销、台账、OA 适配、成本统计、ETC、设置、后台任务等业务服务。

## 前端模块

- 页面在 `web/src/pages/`。
- API client 在 `web/src/features/*/api.ts`。
- 工作台组件在 `web/src/components/workbench/` 和相关 feature 目录。
- 测试在 `web/src/test/`。

## 关键边界

- HTTP 层不应承载复杂业务规则；规则沉淀到 service。
- 生产 API 请求路径只读 PostgreSQL repository/read model，不访问 App Mongo snapshot、GridFS 或 OA Mongo fallback。
- OA 原始库只允许 worker、迁移、shadow-read、audit 工具通过 adapter 只读访问，不让业务服务直接耦合 OA 原始表结构。
- 工作台确认关系以 pair relation 为事实源，不以候选显示状态为事实源。
- 导入文件、预览和确认必须通过导入服务和持久化层统一管理。

## 演进方向

当前系统已经积累大量业务服务，后续生产级性能重构应优先拆出持久化 repository 和 read model 生成器，而不是直接重写业务规则。
