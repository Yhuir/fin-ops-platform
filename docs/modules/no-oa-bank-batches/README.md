# 免 OA 流水批量处理模块

本模块只维护 legacy `/api/no-oa-bank-batches/*` 与 `no_oa_bank_batch` canonical batch/relation state；当前产品页面 `/bank-flow-rule-batches` 不经过本模块。原 no-OA projection、freshness、worker 与 RabbitMQ 链路已退役。

## 维护入口

- 边界与 I/O：`boundary-io.md`
- 状态机：`state-machine.md`
- 测试：`tests.md`
- 实施决策：`implementation-notes.md`
- 全局 read model 合同：`../../architecture/module-boundaries/read-model-contracts.md`

## 代码入口

- `backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`
- `tests/test_no_oa_bank_batch*.py`
