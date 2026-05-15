# 系统架构总览

`fin-ops-platform` 是一个财务运营平台，当前以银企核销、关联工作台、发票/流水导入、OA 集成、税金抵扣、成本统计和 ETC 管理为主。

## 当前形态

- 前端：React + TypeScript + Vite，正式页面在 `web/`。
- 后端：Python 服务，HTTP 入口仍是自定义 server，业务服务集中在 `backend/src/fin_ops_platform/services/`。
- App 状态：生产模式以 MongoDB detailed collections 和 GridFS 持久化为主，保留本地 pickle/JSON 兼容路径。
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
        Workbench pair relations      |
                    |                 |
                    v                 |
        Workbench read models / search|
                    |                 |
                    v                 |
              React 前端页面
```

## 架构原则

- 核销事实必须落到结构化模型，不靠备注表达业务状态。
- 写模型和读模型分离：确认、撤回、异常处理只改最小事实；页面读取优先走物化读模型。
- 外部系统只通过适配层接入，OA 原始库保持只读。
- 导入必须先预览后确认，确认动作必须幂等并可审计。
- 生产操作必须有权限、审计、状态反馈和回滚路径。

## 性能演进方向

当前系统已经拆出 pair relations、read models、candidate matches、dirty scopes 等性能相关模型。后续如果做高性能生产重构，建议优先处理：

1. 将财务主业务事实迁入 PostgreSQL，Mongo 保留为 OA 源读取、附件缓存或非核心读模型。
2. 将 `ApplicationStateStore` 中的整包 snapshot 语义拆成明确 repository。
3. 将工作台、搜索、成本统计、税金抵扣全部改为数据库可索引查询和物化读模型。
4. 将导入、OCR、OA 同步、统计预热迁入后台任务。
5. 对核心接口建立压测基线和 `EXPLAIN ANALYZE` 调优闭环。

详细文档见 `docs/architecture/index.md`。
