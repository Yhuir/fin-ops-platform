# 页面架构与页面间影响关系

日期：2026-08-29

## 代码事实源

- 页面注册：`web/src/app/pageRegistry.tsx`
- 路由 host：`web/src/app/router.tsx`、`web/src/app/PageRouteHost.tsx`
- 页面入口：`web/src/pages/*`
- API clients：`web/src/features/*/api.ts`
- 后端 routes：`backend/src/fin_ops_platform/app/routes_*.py`
- 页面 query services/repositories：`backend/src/fin_ops_platform/services/`

## 页面读取矩阵

| 页面域 | 主要 canonical 来源 | 后台 owner |
| --- | --- | --- |
| 关联台/批量账务 | OA、银行、发票、ETC、active pair relations；合格的无 OA 收入+销项关系可同步派生 relation-scoped 收据 PDF | Workbench matching 只负责领域匹配；收据无 read model/worker |
| 银行明细/余额/流水规则 | 银行流水、分类/标签、账户映射、active relations | settings-maintenance 只负责要求重算 |
| 待找发票/进项使用/销项收款 | 银行流水、发票 lifecycle、规则、active relations | import 只负责导入 |
| OA 待付款 | OA canonical snapshot、银行/发票、active relations | OA sync |
| 税金抵扣/成本统计/外部往来 | 发票、流水、项目、认证/闭环事实、active relations | 明确 import/maintenance job |
| ETC 管理 | ETC tickets、business batches、invoices、OA submit facts | import |
| 设置 | canonical settings/ACL/project/rule versions | settings-maintenance |
| App Health/操作历史 | workers、queue、jobs、audit、HTTP/DB metrics | 运维平面 |

所有业务页面都通过 page-specific repository 直接读取 PostgreSQL canonical facts。需要 rows + summary + facets
的响应必须来自同一 `REPEATABLE READ READ ONLY` snapshot。

## 页面刷新合同

- 初次 mount、query 改变、用户明确刷新和当前页写后一次 GET 是业务读取入口。
- 离开页面会卸载 React tree；不保留隐藏业务 DOM、rows cache 或跨页刷新订阅。
- 普通写不发送 window event/BroadcastChannel，也不触发其它页面请求。
- OA sync/import/maintenance progress 和 App Health 使用自己的 bounded polling，不作为页面事实来源。
- 前端请求必须能 abort/淘汰旧 generation，迟到响应不能覆盖更新的 query/result。

## 页面 I/O 合同

- 输入：tenant/session、bounded filters/sort/page/cursor、业务 version/fingerprint。
- 输出：page-specific DTO、canonical versions、必要的 affected IDs/months。
- GET 不 enqueue、不访问 Redis/RabbitMQ、不返回 projection freshness/generation/job 字段。
- repository 或外部 adapter 不可用时返回明确错误；禁止 fallback 到历史表或旧 payload。
- 金额统一两位小数、不使用千分位；共享 formatter 位于 `web/src/features/money.ts`。

## 页面页头布局合同

- `进项发票使用情况` 的标准页面壳层作为业务页面页头基线：主内容区顶部和左右均使用 `16px` 间距。
- 标准页面通过共享 `PageScaffold` / `page-stack` 承担外层间距；页面根节点不得再次叠加 page padding。
- 页面可以在共享壳层内调整工具栏、表格或内容区，但不得用页面私有 header padding 改变标题起点。
- `关联台` 的沉浸式三栏工作台和 `设置` 的复合导航布局是显式例外，不套用标准业务页头基线。

## 权限

`SessionProvider` 与 backend guards 使用 canonical ACL。前端隐藏/禁用只改善交互，不能替代 API permission。
`YNSYLP005` 是受保护管理员；其它 access/read-export/full-access 账号由设置页维护并投影到 OA 专用角色。
OA role/permission 不反向决定 App tier。

## App Status

Domain registry 为每页映射 route、业务 job 和外部依赖。全局状态展示 session、OA sync、jobs、四个 worker、
queue 和 dependency health；业务页面不展示 Audit 控件，App Health System Audit 集中验证 canonical snapshot 的完整性与关系一致性。

## 维护要求

新增页面或改变事实来源时，同时更新本矩阵、对应模块 `boundary-io.md`、API contract 和回归测试。不得新增
第二数据源、兼容分支、页面缓存 worker 或跨页面协调器。
