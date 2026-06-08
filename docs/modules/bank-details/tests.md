# 银行明细 测试矩阵


> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 待判断 | 待补充 | 业务规则、金额、状态、分类、权限、去重、幂等时适用。 |
| 2. Service-layer tests | 待判断 | 待补充 | service、repository、audit、read model、cache、worker 编排时适用。 |
| 3. API contract tests | 待判断 | 待补充 | HTTP/API contract 或 DTO shape 变化时适用。 |
| 4. Read model/cache/background job tests | 待判断 | 待补充 | list、summary、search、workbench、ledger、import、worker 变化时适用。 |
| 5. Frontend component and interaction tests | 待判断 | 待补充 | 页面、表格、drawer、dialog、按钮、筛选、权限渲染变化时适用。 |
| 6. End-to-end business-flow integration tests | 待判断 | 待补充 | 跨模块业务链路变化时适用。 |
| 7. Existing feature regression tests | 待判断 | 待补充 | 每次变更都要判断受影响旧行为。 |

## 现有验证命令

```bash
# 后端示例，按实际模块替换
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v

# 前端示例，按实际模块替换
cd web && npm test
cd web && npm run build
```

## 未测风险

- 待补充。
