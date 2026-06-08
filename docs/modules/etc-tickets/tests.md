# ETC票据管理 测试矩阵


> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_etc_backend.py` | 覆盖人工确认状态推进、批次上报金额优先、散票折叠规则、已提交批次本地删除后发票释放规则。 |
| 2. Service-layer tests | 适用 | `tests/test_etc_backend.py`、`tests/test_workbench_sql_runtime.py` | 覆盖 ETC business batch service 调用对账任务闭环、repository 落库金额/数量派生、审计和已提交批次 reset 链路。 |
| 3. API contract tests | 适用 | `tests/test_etc_backend.py` | 覆盖 `manual-oa-status` 后响应、submitted bucket、月份筛选按开票/通行日期匹配且 counts 与 items 使用同一筛选口径、Workbench row shape、`DELETE /api/etc/business-batches/{id}` 对已提交批次返回本地 reset 结果。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_etc_backend.py`、`tests/test_workbench_sql_runtime.py` | 覆盖 Workbench projection 从业务批次表生成 open `etc_invoice_summary`、隐藏散票、匹配 OA 时追加汇总行、已提交批次 reset 后 summary 消失且散票恢复，并验证展示金额与结构化 `amount_value`/numeric 金额列同时存在以支持金额搜索。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/EtcTicketManagementPage.test.tsx` | 覆盖单一批次列表、未提交/已提交 tab、tab 计数与当前月份/车牌/关键词筛选下的可见列表一致、人工确认按钮、确认后刷新任务/已提交 bucket、无自动检测入口、已提交批次删除确认文案和 local reset 调用。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_etc_backend.py` | 覆盖导入/批次/人工提交/对账任务闭环/关联台展示/已提交批次本地 reset 的关键路径。 |
| 7. Existing feature regression tests | 适用 | `tests/test_etc_backend.py`、`web/src/test/EtcTicketManagementPage.test.tsx` | 覆盖既有 ETC 页面旧入口、OA 匹配汇总行、删除/文件/补充凭证交互，防止 legacy 撤销提交入口重新暴露。 |

## 现有验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v

cd web && npm test -- --run src/test/EtcTicketManagementPage.test.tsx
cd web && npm run build
```

## 未测风险

- `tests.test_etc_backend` 中依赖本机真实票据样例的用例在样例缺失时会 skip；核心 ETC 业务批次和 Workbench projection 路径不依赖这些样例。
