# 免 OA 流水批次状态机

- `unsubmitted -> submitted`：校验 version/规则，提交 batch 与 canonical relation；零页面 fan-out。
- `submitted -> withdrawn`：撤回 batch 与 relation；零页面 fan-out。
- 合法幂等重复保持当前状态；version conflict 必须 fail fast。
- 页面读取直接查询 canonical batch facts；只有 `loading/empty/error/result`，没有 read-model missing/stale/refreshing/fresh 状态。
