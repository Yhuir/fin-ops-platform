---
status: fixing
trigger: "修复历史附件重复读取并部署 744e1c4d5 后，真实 59 ZIP ETC 发票预览仍在约 62 秒返回 504，页面表现为导入后没反应。"
created: 2026-07-14
updated: 2026-07-14
---

# Debug Session: etc-preview-minio-write-504

## Symptoms

- Expected behavior: task `ETC-RECON-241132` version 19 上传 59 个真实 ETC ZIP 后，preview 在代理时限内返回筛选结果并持久化 durable session。
- Actual behavior: 生产 release `main-744e1c4d5-20260714etc` 接收约 24.98 MB multipart 后，在 62.145 秒返回 Nginx HTML 504；页面没有预览结果。
- Error messages: `504 Gateway Time-out`，响应没有 application request id。
- Timeline: 历史附件 2,344 次 MinIO read 修复已上线，但真实生产 smoke 证明 504 仍存在。
- Reproduction: 将 `发票5、6月.zip` 中 59 个内层 ZIP 逐文件 POST 到 `/api/etc/import/preview`，表单 task_id 为 `ETC-RECON-241132`。

## Current Focus

- hypothesis: confirmed — task-aware preview 的全局需求匹配没有在金额组合搜索前约束车牌与日期窗口，并使用逐候选复制/排序全部中间金额状态的 DP；真实任务 38 个需求、99 张候选中的 14 个多发票需求触发组合爆炸。
- test: 在 `_requirement_match_options` 统一过滤 requirement context，并使用 meet-in-the-middle `(张数, 金额)` 索引生成精确组合、仅保留 deterministic score 最优 64 个；用同一 task payload 和 59 ZIP 复测完整 task-aware preview。
- expecting: 生产 preview 在 60 秒内返回 HTTP 200 和 sessionId；99 张 ZIP 发票按 task 过滤到本次 68 张要求，PostgreSQL/MinIO durable 写入成功。
- next_action: 提交已回归的匹配修复，独立部署并复跑真实 59 ZIP production smoke。
- reasoning_checkpoint:
  - evidence_for: 并发 archive writer 上线后 public preview 仍在 61.918 秒 504，绕过 Nginx 300 秒不返回；回滚版串行请求绕过 Nginx 240 秒同样不返回。生产 API 持续消耗 CPU；本地完整 task-aware preview 的 faulthandler 栈稳定在 `_find_amount_combinations`，而普通 ZIP parser 只需 614ms。
  - evidence_against: archive verified writes 仍属于请求耗时，但不是导致数分钟无响应的主因；修复后仍需真实 PostgreSQL + MinIO smoke 证明总时长低于代理阈值。
  - conclusion: 首轮只测普通 parser 导致误判存储热路径；完整 task-aware 复现证明真正的确定性 root cause 是全局组合候选边界缺失与 DP 算法放大。

## Evidence

- 2026-07-14: 外层归档 SHA-256 为 `7906bd8b8443d06bee09c5d9c100e7f3315a4d4af9e8d24ce8c5b524ef5a11ed`，含 59 个唯一、完整的内层 ZIP，总字节 24,967,628。
- 2026-07-14: 项目 `EtcService.inspect_import_zips` 本地处理 59 ZIP 用时 613.632ms，得到 99 个 unique/importable items、0 error。
- 2026-07-14: 生产 multipart preview 上传 24,978,647 bytes，62.144627 秒收到 Nginx HTML 504。
- 2026-07-14: 504 后 `/health` 的 API performance 未产生 completed preview sample；task 仍为 ready_for_import、hasImportedInvoices=false、importedInvoiceCount=0，确认没有误执行正式导入。
- 2026-07-14: CodeGraph 确认 `save_preview -> store_etc_import_archive -> _store_object_file -> write_verified_object`，每个 archive 顺序执行 2 PUT、2 GET、1 DELETE，并穿插 file-object pending/verified PostgreSQL 写入。
- 2026-07-14: 基于 boto3 官方 client thread-safety 合同曾尝试 4 个 writer；release `main-4a64696c2-etc59parallel-20260714` public smoke 仍在 61.918 秒返回 504，绕过 Nginx 300 秒仍无响应。release 已回滚，诊断请求已通过重启清理。
- 2026-07-14: 回滚串行 release 绕过 Nginx 的同一请求 240 秒仍无响应，排除“只要优化 MinIO 并发即可闭环”。
- 2026-07-14: 真实 task context 过滤后，14 个多发票需求的单需求 eligible candidates 最大仍为 30、invoice_count 最大 6；旧 DP 对每个候选复制所有 sum state，并逐 sum 反复计算组合 score/排序。
- 2026-07-14: 修复后同一生产 task payload + 59 ZIP 的完整 `preview_etc_zip_for_task` 用时 304.158ms，99 个 preview items、68 个 allowed invoice numbers、0 blocking issues。
- 2026-07-14: 95 个 ETC reconciliation tests 与 52 个 ETC service/API/session/object-storage tests 通过；Ruff 与 docs check 通过。

## Eliminated

- 59 个 ZIP 损坏：全部内层 archive 通过完整性检查，且 SHA-256 均不同。
- 普通 ZIP/XML 解析是 60 秒主因：项目真实 parser 处理相同 bytes 低于 1 秒。
- 前端没有发送请求：直接 API smoke 已上传完整 multipart 并复现同一 Nginx 504。
- Nginx 60 秒本身是根因：绕过 Nginx 后同一请求 240/300 秒仍未完成。
- 59 次串行 MinIO/PG verified write 是主因：并发版本与串行版本都在完整 task-aware 匹配阶段长时间占用 CPU；并发改动已撤销。

## Resolution

- root_cause: `_select_global_requirement_matches` 把全量发票候选直接交给多发票金额组合搜索，没有先执行 requirement 的车牌和日期窗口 contract；旧 `_find_amount_combinations` 又在每轮候选上复制、打分和排序全部中间金额状态，真实 38×99 数据形成 CPU 组合爆炸并允许跨上下文误配。
- fix: `_requirement_match_options` 统一先执行 `_invoice_satisfies_requirement_context`；精确张数/金额组合使用 meet-in-the-middle，将候选分半并按 `(张数, 金额)` 合并，只保留 score 最优 64 个完整组合。撤销未经生产验证的并发 session store 改动。
- verification: 新增跨车牌同金额与 30 候选/6 张发票组合回归；95 个 reconciliation tests、52 个 ETC service/API/session/object-storage tests、Ruff、docs check 全部通过。真实 task-aware 本地回归从不收敛降至 304.158ms；生产 PostgreSQL + MinIO smoke 待新 release 部署后完成。
- files_changed: `backend/src/fin_ops_platform/services/etc_reconciliation_zip_filter.py`、`tests/test_etc_reconciliation_service.py`、`backend/src/fin_ops_platform/services/etc_import_session_store.py`、`tests/test_etc_import_session_store.py`、`docs/modules/imports-etc-invoices/{boundary-io.md,tests.md,implementation-notes.md}`。
