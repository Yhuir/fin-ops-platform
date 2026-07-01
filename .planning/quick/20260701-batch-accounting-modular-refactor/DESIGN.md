# 日常报销批量账务管理模块化重构设计

日期：2026-07-01

## 目标

- 修复不是堆砌补丁：把提交写路径从列表读路径中拆出来。
- 每个功能边界有明确 I/O。
- 移除旧逻辑污染：submit 不得再直连整页 relation distribution。

## 本次执行范围

| 模块 | 输入 | 输出 | 本次处理 |
| --- | --- | --- | --- |
| route mutation boundary | HTTP body + OA session | service mutation result + barrier targets | submit 显式使用 SQL read model service factory |
| workbench row context | `bank_year` + Workbench SQL payload fallback | rows/index/invoice links，不含 relation distribution | 新增独立私有入口 |
| list context | workbench row context | eligible bank/OA + relation freshness status | 仅 GET/list 使用整页 relation distribution |
| submit context | workbench row context | 选中 row 校验所需 rows/index/invoice links | submit 使用 scoped row-id readiness，不加载整页 relation distribution |
| relation write | selected row ids + row types + amount check | canonical relation command result | 继续只走 `WorkbenchRelationCommandService` |

## 不做

- 不拆前端组件文件：当前 bug 和性能瓶颈在后端 submit/read boundary。
- 不新增独立 `batch_accounting` read model：先用现有 Workbench SQL active read model，只有 GET p95 调优后仍不达标才上独立 worker/read model。
- 不改 Nginx timeout：504 是后端超时症状，拉长 timeout 不是根因修复。

## 验收

- `POST /api/batch-accounting/submit` 不能调用列表上下文或整页 relation distribution。
- submit relation freshness 只按本次银行/OA/发票 rows 调用。
- GET/list 仍按原合同透出 `read_model_status`、候选过滤、submitted bucket。
- 缺 command service 仍 fail fast，不回退旧 pair relation 写入。
