# 销项发票收款情况 Spec-first E2E Spec

本文件定义 `/output-invoice-collections` 页面在真实浏览器中的业务验收合同。测试必须证明用户可见的销项收款、红蓝票关系和收据流程，而不是保护当前组件实现细节。

## 模块目标

销项发票收款情况页面用于查看销项发票、收入流水、收款状态、红蓝票关系和正式收据生命周期。页面必须只展示 fresh read model 结果；手动状态、提醒、红蓝票关系和收据写入后必须重新读取后端 rows，不能只靠前端局部状态伪装成功。

## 用户角色

- `admin`：可读写并维护收据编号设置。
- `full_access`：可读写收款状态、提醒、红蓝票关系和收据流程。
- `read_export_only`：可查看/导出，不能触发写操作。
- forbidden/expired session：不能进入页面或调用受保护 API。

## Spec 场景

| Spec ID | 场景 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| `OUT-COLL-E2E-001` | fresh rows/filter/table baseline | P0 | 页面加载 fresh rows，展示发票、收款状态、收入流水、收据状态；首屏 page size 有界，筛选/排序不从当前页伪造全局选项。 |
| `OUT-COLL-E2E-002` | 手动收款状态/提醒 -> barrier -> rows refresh | P0 | 保存状态和提醒后，页面等待 `output_invoice_collection` operation barrier fresh，再重新请求 rows，行状态更新为后端返回结果，drawer 关闭且失败不静默吞掉；状态保存暂时失败时必须保留 drawer、用户输入和原 rows，不触发提醒半提交，重试成功后才刷新 rows；若状态已保存成功但提醒保存暂时失败，必须保留 drawer、提醒输入和原 rows，重试时不得重复提交未改变的状态 payload，提醒成功后才刷新 rows。 |
| `OUT-COLL-E2E-003` | 正式收据 preview/create/void/reissue/history | P0 | 预览展示收据信息，创建必须带 idempotency key；创建、作废和重开后等待 `output_invoice_collection` barrier，再 rows refresh，history 展示真实 receipt fact 和状态变化；创建暂时失败时必须保留预览 drawer、错误和重试入口，不能提前进入已出收据或读取伪历史；作废/重开暂时失败时必须保留原因弹窗、用户输入和当前 history，不得提前刷新 rows/history。 |
| `OUT-COLL-E2E-004` | 红蓝票关系 confirm/revoke -> barrier -> relation overlay | P0 | 选择关联发票并确认后，页面等待 `output_invoice_collection` barrier，再重新读取 rows，红蓝票 drawer 的已有依据展示人工关系、来源和证据；撤销后该人工依据消失。 |
| `OUT-COLL-E2E-005` | read model refreshing/stale | P0 | missing/stale/source mismatch 不显示 stale rows 为 fresh；页面展示 loading/refreshing/empty/error 的用户可理解状态并自动重试。 |
| `OUT-COLL-E2E-006` | 权限和 admin-only 设置 | P1 | `read_export_only` 不触发写 API，`admin` 才显示收据编号设置；API 403 不被 UI 当作成功。 |
| `OUT-COLL-E2E-007` | 导出/download | P1 | 浏览器 download event 成功，字段、筛选、权限和 row-limit 反馈与后端 contract 一致。 |
| `OUT-COLL-E2E-008` | 下游 tax/cost/search fan-out | P1 | 红蓝票、收款状态或 receipt 变化后，下游税金、成本和搜索等页面通过自己的 read model 展示一致结果。 |

## 不属于本地 deterministic E2E 的风险

- 真实 PostgreSQL 大数据、历史半迁移、EXPLAIN 和锁等待。
- 真实 RabbitMQ/Redis/systemd worker drain。
- 真实生产下载保存、浏览器 profile 权限和大文件导出性能。
- 真实税金/成本/search 全量链路需要 staging 或生产前 smoke。
