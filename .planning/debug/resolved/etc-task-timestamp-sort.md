---
status: resolved
trigger: "新建 ETC 批次后，批次流程显示接口处理失败；用户要求修复并保证 ETC 整个链路恢复通畅。"
created: 2026-07-14
updated: 2026-07-14
---

# Symptoms

- Expected: 新建 ETC business batch 后，批次流程和 ETC 发票导入 ready task 均可读取，后续导入链路可继续。
- Actual: business batch 与新 task 创建成功，但 reconciliation task list 和 ready-for-import 均返回 HTTP 500。
- Error: `TypeError: '<' not supported between instances of 'NoneType' and 'datetime.datetime'`。
- Timeline: migration `0101_phase19_audit_contract_boundaries.sql` 上线并重启 API 后出现。
- Reproduction: 生产存在 migration 补建的历史 task 与正常新 task 时，请求任一 reconciliation task 聚合列表。

# Current Focus

- hypothesis: migration 0101 的历史 task raw payload 缺少 created_at/updated_at，repository 丢弃正式表列时间，hydrate 生成 None，聚合列表排序失败。
- test: 用历史空时间 task + 正常新 task 复现两个列表异常；修复后同形数据必须稳定排序且两个 API 返回 200。
- expecting: 仅恢复 task 时间合同，不改变业务状态、版本、发票、OA、关联关系或 worker/read model 语义。
- next_action: none; production migration, API stability, page audits, worker readiness, and regression suites are green.

# Evidence

- timestamp: 2026-07-14T02:40:00+08:00
  fact: production business batch `etc_business_batch_241130` and task `ETC-RECON-241130` are readable individually.
- timestamp: 2026-07-14T02:40:00+08:00
  fact: request IDs `1ea545fe84e6` and `62a176ca63f0` both failed in aggregate sorting with NoneType/datetime comparison.
- timestamp: 2026-07-14T02:45:00+08:00
  fact: local migration-shaped snapshot reproduced both failures exactly.
- timestamp: 2026-07-14T02:47:00+08:00
  fact: regression tests failed before 0103 existed and passed after the migration was added.
- timestamp: 2026-07-14T02:49:00+08:00
  fact: disposable PostgreSQL applied migrations 0001-0103; 0103 ran twice idempotently and mixed historical/current task list plus ready-list both passed.
- timestamp: 2026-07-14T02:57:00+08:00
  fact: production release main-etc-tsfix-7db51e06-20260714025429 applied migration 0103 in 54ms and restarted API plus registered workers successfully.
- timestamp: 2026-07-14T03:02:00+08:00
  fact: production task list, ready-for-import, current task detail, historical task detail, active/submitted batches, ETC page Audit, and ETC import Audit all returned JSON 200; both audits passed with fresh/drained state.
- timestamp: 2026-07-14T03:04:00+08:00
  fact: five repeated production reads of task list, ready-for-import, and active business batches all returned JSON 200 with stable task counts; post-release logs contained no NoneType, traceback, or ETC 500 match.

# Eliminated

- hypothesis: 新建 business batch 或新 task 本身写入失败。
  reason: 两者均可通过生产单条 API 读取，状态和版本正确。
- hypothesis: Nginx、权限、RabbitMQ 或 ETC 页面 read model 故障。
  reason: 同一身份可读取 business batch 和单 task；异常发生在 API 进程内 Python 排序。

# Resolution

- root_cause: migration 0101 inserted historical imported task payloads without created_at/updated_at; the repository hydrates from raw payload, so mixed historical/current task ordering compared None with datetime.
- fix: forward migration 0103 copies only missing normalized payload timestamps from the same row's typed canonical columns; no sort fallback and no state/read-model/worker change.
- verification: static and disposable PostgreSQL migration regressions green; 416-test ETC/API/service set green after pin update, 457 worker/Workbench/Audit tests green, 153 frontend tests green, 13 Chromium ETC/ETC-import flows green, lint/build/docs green, production release and five-round API stability checks green.
- files_changed: migration 0103, migration pinning tests, PostgreSQL integration regression, ETC/canonical/operations docs.
