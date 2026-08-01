# 系统架构总览

`fin-ops-platform` 是一个财务运营平台，当前以银企核销、关联工作台、发票/流水导入、OA 集成、税金抵扣、成本统计和 ETC 管理为主。

## 当前形态

- 前端：React + TypeScript + Vite，正式页面在 `web/`。
- 后端：Python WSGI 服务，由 Gunicorn `gthread` 运行；`http_adapter.py` 负责请求边界，业务服务集中在 `backend/src/fin_ops_platform/services/`。
- App 状态：PostgreSQL 是生产 app 状态和业务事实的唯一读写库；当前 runtime 不读取 app Mongo，也没有 app Mongo fallback、shadow-read 或导出/审计旁路。
- OA 数据源：通过 `MongoOAAdapter` 只读读取 OA MongoDB。
- 部署：当前已有 OA 同域部署资产，前端路径 `/fin-ops/`，后端路径 `/fin-ops-api/`。

## 核心模块

| 模块 | 职责 | 主要文档 |
| --- | --- | --- |
| 导入与标准化 | Excel/文件导入、预览、确认、幂等防重 | `docs/product-specs/imports.md` |
| 关联工作台 | OA、银行流水、发票三栏关联、确认、撤回、异常处理 | `docs/product-specs/workbench.md` |
| 核销与台账 | 核销单、核销明细、台账、提醒、往来关系 | `docs/product-specs/reconciliation.md` |
| 异常处理 | 结构化异常 case、规则分类、处理动作和审计 | `docs/product-specs/exception-handling.md` |
| 税金与 ETC | 税金抵扣、已认证发票、ETC 票据导入与对账 | `docs/product-specs/tax-offset-and-etc.md` |
| 成本统计 | 项目/月份/费用类型统计、下钻和导出 | `docs/product-specs/cost-statistics.md` |
| OA 集成 | 登录复用、菜单 iframe、账户权限、OA 源数据同步 | `docs/architecture/oa-integration.md` |
| 后台任务与健康 | 长任务、预热、重试、告警、状态栏 | `docs/product-specs/app-health-and-background-jobs.md` |

## 数据流

```text
OA MongoDB       Excel/PDF/ZIP 导入
   |                    |
   v                    v
OA Adapter       Import/File Services
   |                    |
   +------> 业务服务与状态投影 <------+
                    |                 |
                    v                 |
              PostgreSQL app store
                 |             |
                 |             +----> 页面专属 canonical query ----> React 前端页面
                 v
        Workbench pair relations
                 |
                 v
          两个登记 read model
                 |
                 v
        关联台及登记的独立消费者
```

## 架构原则

- 核销事实必须落到结构化模型，不靠备注表达业务状态。
- 写入只改变最小 canonical 事实。除关联台外，财务页面通过页面专属 query service 在单个只读快照中直接读取 canonical facts 和 active relations；只有 `workbench` 与 `workbench_relation` 两个明确登记的 read model 使用 freshness/status/enqueue/worker 合同。工作台采用 generation 原子发布，刷新期间只暴露最近 active generation，不读取 building/failed 中间状态。
- 外部系统只通过适配层接入，OA 原始库保持只读。
- 导入必须先预览后确认，确认动作必须幂等并可审计。
- 生产操作必须有权限、审计、状态反馈和回滚路径。

## 性能演进方向

当前系统已经拆出 pair relations、read models、candidate matches、dirty scopes 等性能相关模型。后续如果做高性能生产重构，建议优先处理：

1. 持续优化页面专属 canonical query 的 SQL、索引和批量读取，保持单快照一致性并建立 p95/p99 基线。
2. 生产业务 I/O 继续收敛到明确 service/repository；`ApplicationStateStore` 仅保留本地 tooling/test 用途，不参与生产事实读取。
3. 只优化已登记的两个 read model，不为已直读页面或已删除的 Search API 恢复 projection/worker；工作台 Redis page cache 以 freshness gate 通过后的 active generation 为版本边界。
4. 导入、OCR、OA 同步、设置数据重置和启动恢复均由 durable worker/显式 maintenance 执行，API 启动不隐式运行这些任务。
5. 对核心接口建立压测基线和 `EXPLAIN ANALYZE` 调优闭环。

## HTTP 运行时边界

- systemd 只启动 Gunicorn，不再启动 `ThreadingHTTPServer`。当前使用单个有界 `gthread` worker，保持现有进程内 command state 的一致性；并发、backlog、worker recycling、graceful timeout 都由 Gunicorn 配置约束。
- WSGI adapter 在业务分发前校验 `Content-Length` 和按内容类型区分的 body 上限，生成/透传 request ID，并把数据库连接池 backpressure 映射为可重试 `503`。
- PostgreSQL pool 有明确 acquire timeout、max waiting 和 pool metrics；Nginx 同时限制 client body、连接及 upstream timeout。
- 当前状态通知统一使用有界 HTTP polling；旧 App Health/Workbench SSE routes、前端 `EventSource` 和 SSE smoke 已删除。

详细文档见 `docs/architecture/index.md`。
