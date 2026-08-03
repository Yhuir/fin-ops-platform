# App 架构维护入口

本目录记录当前 app 的运行架构事实。它用于日常开发时快速判断页面、API、service、read model、worker 和跨页面刷新之间的关系。

## 维护范围

| 文件 | 用途 |
| --- | --- |
| `pages.md` | 页面路由、组件入口、API client、刷新来源和页面间影响关系。 |
| `runtime-and-ownership.md` | HTTP/WSGI 调用链、dirty/outbox、read model refresh、worker、轮询/App Health 和模块 owner。 |
| `docs-maintenance.md` | 文档维护规则、删除归档规则和核心设计原则。 |

页面或功能域的日常维护入口在 `../modules/`。修改或新增功能前，先按 `../modules/README.md` 定位目标模块，再回到本目录和其他长期事实源校验页面、API、read model、worker 和跨页面影响关系。

## 当前代码事实源

- 前端页面注册表：`web/src/app/pageRegistry.tsx`
- 前端路由 host：`web/src/app/router.tsx`、`web/src/app/PageRouteHost.tsx`
- 侧边栏导航：`web/src/components/shell/sidebarItems.ts`（从页面注册表派生）
- 页面入口：`web/src/pages/*`
- 前端 API client：`web/src/features/*/api.ts`
- 后端 HTTP adapter：`backend/src/fin_ops_platform/app/http_adapter.py`、`backend/src/fin_ops_platform/app/wsgi.py`
- 后端 HTTP 分发：`backend/src/fin_ops_platform/app/server.py`
- 后端 route modules：`backend/src/fin_ops_platform/app/routes_*.py`
- 派生数据生命周期：`backend/src/fin_ops_platform/services/derived_data_lifecycle_service.py`
- Read model freshness gateway：`backend/src/fin_ops_platform/services/read_model_query_gateway.py`
- Durable queue：`backend/src/fin_ops_platform/services/runtime_queue.py`
- Worker registry：`backend/src/fin_ops_platform/services/runtime_worker_registry.py`

## 页面读取合同

成本统计、银行明细、OA 待付款、流水规则批量处理、批量账务、ETC、税金抵扣、待找发票、进项使用、销项收款与外部往来款都是登记的 page-specific canonical direct-read 页面。页面 query facade/repository 在单个 `REPEATABLE READ READ ONLY` PostgreSQL snapshot 内组合 canonical facts 与 active formal relations，不消费页面 read model、Redis、refresh status、queue 或 worker。

关联台是唯一仍使用页面 read model 的财务页面：继续使用 `workbench` active-generation read model、freshness/status/enqueue、Redis fresh cache 和 Workbench worker。`workbench_relation` 作为唯一共享 relation distribution read model，继续服务仍登记的独立消费者。Search API/index runtime 已删除；legacy no-OA 列表改为请求内 canonical query，不再依赖 projection、freshness 或 worker。

## 金额展示与搜索合同

- APP 内业务金额统一显示两位小数且不使用千分位分隔符，例如 `4311.00`；计数、比例、日期、账号、发票号和导出文件的原始数值合同不受此规则影响。
- 前端金额展示统一复用 `web/src/features/money.ts`，不得在页面新增 `Intl.NumberFormat`、`toLocaleString` 或正则插入逗号的并行金额 formatter。
- 页面 keyword/search 对纯金额查询先移除合法千分位逗号；canonical SQL/search 文本包含原始 numeric 字段的无分组文本。普通含逗号业务文本保持原样，禁止为金额搜索新增 Search API、cache、worker 或逐行 I/O。

## 使用规则

新增或修改页面、API、read model、worker 或 derived lifecycle 事件时，先做文档影响评估；影响当前事实源时更新本目录和对应产品、开发或运维文档。历史 prompt、阶段计划和旧归档不再作为当前事实源。
