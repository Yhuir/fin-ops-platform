# ETC票据管理 测试矩阵


> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_etc_backend.py` | 覆盖人工确认状态推进、批次上报金额优先、散票折叠规则。 |
| 2. Service-layer tests | 适用 | `tests/test_etc_backend.py`、`tests/test_workbench_sql_runtime.py` | 覆盖 ETC business batch service 调用对账任务闭环、repository 落库金额/数量派生和审计相关链路。 |
| 3. API contract tests | 适用 | `tests/test_etc_backend.py` | 覆盖 `manual-oa-status` 后响应、submitted bucket、Workbench row shape。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_etc_backend.py`、`tests/test_workbench_sql_runtime.py` | 覆盖 Workbench projection 从业务批次表生成 open `etc_invoice_summary`、隐藏散票、匹配 OA 时追加汇总行。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/EtcTicketManagementPage.test.tsx` | 覆盖单一批次列表、未提交/已提交 tab、人工确认按钮、确认后刷新任务/已提交 bucket、无自动检测入口。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_etc_backend.py` | 覆盖导入/批次/人工提交/对账任务闭环/关联台展示的关键路径。 |
| 7. Existing feature regression tests | 适用 | `tests/test_etc_backend.py`、`web/src/test/EtcTicketManagementPage.test.tsx` | 覆盖既有 ETC 页面旧入口、OA 匹配汇总行、删除/文件/补充凭证交互。 |

## 现有验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v

cd web && npm test -- --run src/test/EtcTicketManagementPage.test.tsx
cd web && npm run build
```

## 未测风险

- `tests.test_etc_backend` 中依赖本机真实票据样例的用例在样例缺失时会 skip；核心 ETC 业务批次和 Workbench projection 路径不依赖这些样例。
