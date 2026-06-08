# 关联台 测试矩阵


> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_etc_backend.py` 及 Workbench 相关测试 | ETC 汇总行金额、状态和配对边界属于业务规则。 |
| 2. Service-layer tests | 适用 | `tests/test_etc_backend.py` | 覆盖 ETC 人工提交触发 Workbench 投影可见性的服务编排。 |
| 3. API contract tests | 适用 | `tests/test_etc_backend.py` | 覆盖 Workbench rows 中 `source_kind=etc_invoice_summary`、pending relation 和 grouped OA 汇总行。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_etc_backend.py` | 覆盖 projection 隐藏散票、生成 open 汇总行、匹配 OA 时追加汇总行。 |
| 5. Frontend component and interaction tests | 按变更判断 | 关联台页面测试、ETC 页面测试 | 本次 ETC 页面测试覆盖入口侧行为；关联台 UI 若改展示需补 Reconciliation 测试。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_etc_backend.py` | 覆盖 ETC 批次人工提交后进入关联台 open 区等待三项配对。 |
| 7. Existing feature regression tests | 适用 | `tests/test_etc_backend.py` | 覆盖既有 OA 匹配汇总和 open/paired 边界不回退。 |

## 现有验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend -v
cd web && npm run build
```

## 未测风险

- 本矩阵只记录 ETC 汇总行影响的关联台路径；其他 Workbench 配对模式仍以对应模块测试为准。
