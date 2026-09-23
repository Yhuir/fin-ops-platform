# App 架构维护入口

本目录记录当前 app 的运行架构事实。它用于日常开发时快速判断页面、API、service、canonical repository、worker 和跨页面影响关系。

## 维护范围

| 文件 | 用途 |
| --- | --- |
| `pages.md` | 页面路由、组件入口、API client、刷新来源和页面间影响关系。 |
| `runtime-and-ownership.md` | HTTP/WSGI 调用链、durable job、worker、轮询/App Health 和模块 owner。 |
| `docs-maintenance.md` | 文档维护规则、删除归档规则和核心设计原则。 |

页面或功能域的日常维护入口在 `../modules/`。修改或新增功能前，先按 `../modules/README.md` 定位目标模块，再回到本目录和其他长期事实源校验页面、API、canonical I/O、worker 和跨页面影响关系。

## 当前代码事实源

- 前端页面注册表：`web/src/app/pageRegistry.tsx`
- 前端路由 host：`web/src/app/router.tsx`、`web/src/app/PageRouteHost.tsx`
- 侧边栏导航：`web/src/components/shell/sidebarItems.ts`（从页面注册表派生）
- 页面入口：`web/src/pages/*`
- 前端 API client：`web/src/features/*/api.ts`
- 后端 HTTP adapter：`backend/src/fin_ops_platform/app/http_adapter.py`、`backend/src/fin_ops_platform/app/wsgi.py`
- 后端 HTTP 分发：`backend/src/fin_ops_platform/app/server.py`
- 后端 route modules：`backend/src/fin_ops_platform/app/routes_*.py`
- Durable queue：`backend/src/fin_ops_platform/services/runtime_queue.py`
- Worker registry：`backend/src/fin_ops_platform/services/runtime_worker_registry.py`

## 导入运行链

三个导入页面共用 `ImportWorkflowService` 与 `job.import_jobs` 生命周期；领域解析和写入分别由普通文件/ETC 模块负责。上传原件与登记任务后返回 202，import worker 直接领取 prepare 任务，持久预览后等待确认。确认固化本次范围和版本，worker 在领域事务中同时提交事实、来源、审计和任务成功状态。旧 import outbox 中转与独立 BackgroundJob 状态写入已退役；税务认证和 OA 手动导入也使用同一直接队列。

HTTP 只读取当前请求的会话上下文，worker 为每次执行创建独立领域上下文；禁止把某个请求的会话覆盖到共享 Application 服务。ETC 原件解析与附件准备在短财务事务之外，最终成员/附件引用、metadata、task/session 与 job 原子提交。页面直接读 canonical facts，导入不恢复已退役的页面 read model。全局进度读取任务摘要，可显式恢复 owner 的预览。详细 I/O 见[API 契约](../dev/api-contracts.md)及三个导入模块。

## 页面读取合同

成本统计、银行明细、OA 待付款、流水规则批量处理、批量账务、ETC、税金抵扣、待找发票、进项使用、销项收款与外部往来款都是 page-specific canonical direct-read 页面。页面 query facade/repository 在单个 `REPEATABLE READ READ ONLY` PostgreSQL snapshot 内组合 canonical facts 与 active formal relations，不消费 projection、Redis、refresh status、queue 或 worker。

关联台同样使用 page-specific canonical direct-read：`WorkbenchQueryFacade` 在一个
`REPEATABLE READ READ ONLY` snapshot 中查询 canonical facts、active formal relations
与异常决策；页面不再拥有 active generation、freshness/status/enqueue、Redis payload
cache 或专属 worker。其它页面也直接读取相同 canonical relation；`workbench-matching` 是
canonical relation producer，不属于页面读取链。Search API/index runtime 已删除；legacy no-OA 列表也在请求内
直接查询 canonical facts。

## 金额展示与搜索合同

- APP 内业务金额统一显示两位小数且不使用千分位分隔符，例如 `4311.00`；计数、比例、日期、账号、发票号和导出文件的原始数值合同不受此规则影响。
- 前端金额展示统一复用 `web/src/features/money.ts`，不得在页面新增 `Intl.NumberFormat`、`toLocaleString` 或正则插入逗号的并行金额 formatter。
- 页面 keyword/search 对纯金额查询先移除合法千分位逗号；canonical SQL/search 文本包含原始 numeric 字段的无分组文本。普通含逗号业务文本保持原样，禁止为金额搜索新增 Search API、cache、worker 或逐行 I/O。

## 使用规则

新增或修改页面、API、canonical repository、worker 或 domain job 时，先做文档影响评估；影响当前事实源时更新本目录和对应产品、开发或运维文档。历史 prompt、阶段计划和旧归档不再作为当前事实源。

## 持久化流水拆分（2026-09-23）

银行金额、余额及导入身份保留原金融事实。拆分子项通过统一银行 owner 写入，业务用途消费者统一读取子项视图；列表合并显示原流水，抽屉共用同一持久化编辑器。详见 [I/O 与测试矩阵](../dev/bank-transaction-splits.md)。
