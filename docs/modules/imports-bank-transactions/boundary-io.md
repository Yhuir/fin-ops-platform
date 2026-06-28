# 银行流水导入模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：partial
- 当前边界可信度：medium
- 目标边界：银行流水导入通过 import file/service/job queue 进入预览、确认、后台处理和 derived lifecycle，不直接写页面 read model。
- 当前缺口：导入服务影响 bank detail、workbench、search 等多个下游 scope，变更必须同步 fan-out 测试。
- 旧代码删除条件：旧同步导入路径不再被页面/API/脚本引用。

## 职责边界

### 负责

- 银行流水文件上传、模板识别、预览、确认导入、导入任务状态。
- 通过后台任务和 lifecycle 触发 Workbench、invoice lifecycle、成本统计等下游 direct refetch/runtime impact；银行明细页面 direct API 重读银行流水事实。
- 记录导入预览审计。
- 后端导入确认结果或完成后的 job result 仅透出 `affected_scope_keys` 用于写后影响 scope 诊断；不再要求 `bank_detail:<month>` 或 `bank_account_balance:all` read-model scope。前端共享导入页和 background job mapper 不再暴露或消费 affected scope fields，确认成功后直接请求 Workbench 当前月。

### 不负责

- 不直接维护银行明细页面投影。
- 不负责 no-OA、turnover 或 workbench 业务状态机。
- 不绕过 import job queue 执行长任务。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 上传文件/模板选择 | `ImportBankTransactionsPage.tsx` | 文件只进入 import API/service |
| 预览确认 | `ImportWorkflowPage.tsx`、`features/imports/api.ts` | 确认后创建可追踪 job |
| Job event | runtime worker handlers | 后台处理必须可恢复 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 预览结果 | 前端导入页面 | 不持久化为业务事实直到确认 |
| 导入 job status | background job/app status | 可查询、可失败恢复 |
| Runtime impact envelope | derived lifecycle/runtime queue | Workbench、Workbench relation、invoice lifecycle、cost 等下游影响诊断；银行明细和 Search 通过 direct API 重新读取业务结果 |
| Write scope envelope | 后端导入响应/job result 诊断 | 后端仅返回 `affected_scope_keys` 作为写后影响 scope 诊断；不再返回 legacy target fields，消费 completed job 的页面直接重读业务 GET |

## 持久化与投影

- Own read model：无独立 manifest entry。
- 影响页面：Workbench/matching、invoice/cost/search affected domains 或真实后台任务信号；`bank_detail`、`bank_account_balance` 和 Search 不再是 refresh/read model target，只受 direct payload 影响。
- Worker：import job/runtime worker handlers。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/imports/ImportBankTransactionsPage.tsx` |
| Frontend components | `web/src/components/imports/ImportWorkflowPage.tsx` |
| Frontend feature | `web/src/features/imports/api.ts`、`types.ts`、`importRoutes.ts` |
| Backend route | import endpoints in `backend/src/fin_ops_platform/app/server.py` |
| Backend service | `import_file_service.py`、`imports.py`、`import_processing_service.py`、`import_job_queue.py`、`import_preview_audit.py` |
| Worker/lifecycle | `runtime_worker_handlers.py`、`derived_data_lifecycle_service.py`、`app_status_job_registry.py` |
| Tests | `tests/test_import*.py`、`web/src/test/ImportsApi.test.ts`、`web/e2e/imports-bank-transactions-flow.spec.ts` |

## 依赖方向

- 允许依赖：import job queue, background job service, derived lifecycle。
- 必须通过：import service and job queue。
- 禁止绕过：导入确认时直接写 read model；长任务直接跑在 HTTP request 中。

## 测试与验证

- `tests/test_import_api.py`
- `tests/test_import_job_queue.py`
- `tests/test_import_processing_service.py`
- `web/src/test/BackgroundJobProgress.test.tsx`
- `web/src/test/ImportsApi.test.ts`
- `web/e2e/imports-bank-transactions-flow.spec.ts`

## 当前缺口和删除条件

- 模板识别变更必须覆盖预览、确认、失败恢复和 downstream direct payload/background-task convergence。
- 删除旧同步导入路径前，必须证明确认响应/job result 后端诊断仍能覆盖 Workbench、invoice lifecycle、cost 等实际下游影响；前端不得重新暴露或依赖 legacy target wait / affected scope 等待。
