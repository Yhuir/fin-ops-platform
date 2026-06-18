# 成本统计 Spec-first E2E Spec

本文件定义 `/cost-statistics` 页面在真实浏览器中的业务验收合同。测试必须证明成本归因、项目范围、下钻、导出反馈和跨页面 relation fan-out 符合业务规格，而不是保护当前组件实现细节。

## 模块目标

成本统计页面面向项目和期间展示费用、发票、流水和核销关系。页面负责筛选、切换视图、下钻和导出反馈；金额归因、项目归属、candidate/linked relation 语义和 read model freshness 必须来自后端 cost attribution/read model 边界。页面不能把关联台 open/proposed candidate 当作 confirmed 成本事实，也不能把 stale/missing read model 伪装成 fresh。

## 用户角色

- `admin`：可读取、导出，并执行全局设置/运维入口。
- `full_access`：可读取成本统计、查看流水详情和导出。
- `read_export_only`：可读取和导出，不能触发任何写操作。
- forbidden/expired session：不能进入页面或调用受保护 API。

## Spec 场景

| Spec ID | 场景 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| `COST-E2E-001` | fresh time/project/bank/expense baseline | P0 | 页面加载 fresh explorer，按时间、项目、银行和费用类型展示一致金额；首屏不从前端伪造金额或项目范围。 |
| `COST-E2E-002` | project scope active/all | P0 | 默认 `active` 排除已完成项目；切换到 `all` 必须请求 `project_scope=all` 并展示已完成项目。 |
| `COST-E2E-003` | project/expense/transaction drilldown | P0 | 用户可从项目进入费用类型，再进入对应流水，详情 modal 展示后端返回的流水和成本字段。 |
| `COST-E2E-004` | export preview / row-limit feedback | P0 | 导出中心使用当前 view/project scope/filter 请求 preview；后端行数上限错误必须在浏览器中展示结构化消息。 |
| `COST-E2E-005` | Workbench cost-bearing relation fan-out | P0 | 关联台 open candidate 不进入成本项目、金额或明细；确认 OA+bank+invoice 成本关系后，成本页重新读取并展示对应项目、金额、流水和详情。 |
| `COST-E2E-006` | read model refreshing/stale/failed | P0 | explorer/month/export/detail 在 missing/stale/failed/unavailable 时展示刷新或错误语义，不把空 payload 当最终空结果。 |
| `COST-E2E-007` | 权限与导出 gate | P1 | `read_export_only` 能查看/导出但不能触发写操作；API 403 不被 UI 当作成功。 |
| `COST-E2E-008` | large table / visual stability | P1 | 大项目、大费用类型和宽表在真实浏览器中不遮挡、不丢行、滚动可用。 |
| `COST-E2E-009` | real download event | P1 | 浏览器 download event 成功，文件名、筛选、字段、权限和 row-limit contract 与后端一致。 |
| `COST-E2E-010` | downstream/import/settings fan-out | P1 | 导入确认、项目范围设置、turnover/no-OA/ETC 等成本相关写入后，成本统计通过自己的 read model 展示一致结果。 |

## 不属于本地 deterministic E2E 的风险

- 真实生产 PostgreSQL scope cleanup `--apply` 和历史脏数据修复。
- 真实 RabbitMQ/Redis/systemd `cost-statistics` worker drain。
- 真实大数据导出文件保存、打开、耗时和浏览器视觉性能。
- 真实 OA、ETC、turnover、no-OA 和 import 全链路到成本统计的 staging/生产最终收敛。
