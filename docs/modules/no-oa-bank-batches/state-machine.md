# 免 OA 流水批次状态机

- `unsubmitted -> submitted`：校验 version/规则，提交 batch 与 canonical relation；零页面 fan-out。
- `submitted -> withdrawn`：撤回 batch 与 relation；零页面 fan-out。
- 合法幂等重复保持当前状态；version conflict 必须 fail fast。
- 页面读取 missing/stale 时进入 `refreshing`，worker 发布精确月份后进入 `fresh`；写命令不等待该转换。
