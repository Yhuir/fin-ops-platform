# Prompt 33：让税金抵扣读取真实已认证结果并驱动计划锁灰

目标：让税金抵扣页不再读取写死 `certified_items`，而是读取真实导入的已认证结果，并驱动 `进项票认证计划` 的锁灰状态与试算。

前提：

- `32-tax-offset-certified-import-parser-and-storage.md` 已完成

要求：

- `/api/tax-offset` 必须读取真实已认证导入结果
- `/api/tax-offset/calculate` 必须按真实已认证结果试算
- 匹配优先级至少支持：
  - 数电发票号码
  - 发票代码 + 发票号码
  - 销方税号 / 销方名称 + 开票日期 + 税额
- 把结果分成：
  - `certified_matched_rows`
  - `certified_outside_plan_rows`
  - `locked_certified_input_ids`
- 匹配到计划票后：
  - 计划票状态变为 `已认证`
  - 计划票在前端可锁灰
- 未进入计划的已认证票：
  - 出现在右侧抽屉
  - 自动计入试算

建议文件：

- `backend/src/fin_ops_platform/services/tax_offset_service.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_tax_offset_service.py`
- `tests/test_tax_offset_api.py`

交付要求：

- 税金抵扣页后端不再依赖写死已认证样例
- 已认证结果与计划、抽屉、试算三者口径一致

验证：

- 后端测试覆盖匹配、锁灰、outside-plan、试算

