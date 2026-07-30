# 系统架构总览

`fin-ops-platform` 是一个财务运营平台，当前以银企核销、关联工作台、发票/流水导入、OA 集成、税金抵扣、成本统计和 ETC 管理为主。

## 当前形态

- 前端：React + TypeScript + Vite，正式页面在 `web/`。
- 后端：Python 服务，HTTP 入口仍是自定义 server，业务服务集中在 `backend/src/fin_ops_platform/services/`。
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
        四个登记 read model / search
                 |
                 v
        关联台及登记的独立消费者
```

## 架构原则

- 核销事实必须落到结构化模型，不靠备注表达业务状态。
- 写入只改变最小 canonical 事实。除关联台外，财务页面通过页面专属 query service 在单个只读快照中直接读取 canonical facts 和 active relations；只有 `workbench`、`workbench_relation`、`search`、`no_oa_bank_batch` 四个明确登记的 read model 使用 freshness/status/enqueue/worker 合同。工作台采用 generation 原子发布，刷新期间只暴露最近 active generation，不读取 building/failed 中间状态。
- 外部系统只通过适配层接入，OA 原始库保持只读。
- 导入必须先预览后确认，确认动作必须幂等并可审计。
- 生产操作必须有权限、审计、状态反馈和回滚路径。

## 性能演进方向

当前系统已经拆出 pair relations、read models、candidate matches、dirty scopes 等性能相关模型。后续如果做高性能生产重构，建议优先处理：

1. 持续优化页面专属 canonical query 的 SQL、索引和批量读取，保持单快照一致性并建立 p95/p99 基线。
2. 生产业务 I/O 继续收敛到明确 service/repository；`ApplicationStateStore` 仅保留本地 tooling/test 用途，不参与生产事实读取。
3. 只优化已登记的四个 read model，不为已直读页面恢复 projection/worker；工作台 Redis page cache 以 freshness gate 通过后的 active generation 为版本边界。
4. 将导入、OCR、OA 同步、统计预热迁入后台任务。
5. 对核心接口建立压测基线和 `EXPLAIN ANALYZE` 调优闭环。

详细文档见 `docs/architecture/index.md`。
