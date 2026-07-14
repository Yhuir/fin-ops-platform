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

- hypothesis: confirmed — preview 的 59 个 archive 在 HTTP 请求内串行执行 temporary PUT/GET、final PUT/GET 和 PostgreSQL file-object registration；即使移除历史附件 read 与最终整批 reload，verified write 总耗时仍超过 Nginx 60 秒。
- test: 固定最多 4 个并发 writer，保持每个对象的完整 verified-write 合同、原 ordinal 顺序、全部成功后单次 session commit 和失败时全量成功对象清理；部署后使用同一 59 ZIP 复测。
- expecting: 生产 preview 在 60 秒内返回 HTTP 200 和 sessionId；99 张 ZIP 发票按 task 过滤到本次 68 张要求，PostgreSQL/MinIO durable 写入成功。
- next_action: 完成目标回归、独立提交/部署并复跑真实 59 ZIP production smoke。
- reasoning_checkpoint:
  - evidence_for: 同一 59 ZIP 使用项目 parser 本地解析 99 张发票仅 614ms；生产 HTTP 上传 24.98 MB 后稳定约 62 秒由 Nginx 终止；当前 `save_preview` 仍按 upload 串行调用 verified object storage。
  - evidence_against: 尚未取得本次后端完成时间和分阶段生产 telemetry，不能仅凭源码把全部剩余时间归给 MinIO。
  - conclusion: 59 次串行 verified writes 是首轮优化后仍存在的确定性 latency root cause；采用低于 PG pool 上限的 4 路并发是保持 I/O 合同的最小修复。

## Evidence

- 2026-07-14: 外层归档 SHA-256 为 `7906bd8b8443d06bee09c5d9c100e7f3315a4d4af9e8d24ce8c5b524ef5a11ed`，含 59 个唯一、完整的内层 ZIP，总字节 24,967,628。
- 2026-07-14: 项目 `EtcService.inspect_import_zips` 本地处理 59 ZIP 用时 613.632ms，得到 99 个 unique/importable items、0 error。
- 2026-07-14: 生产 multipart preview 上传 24,978,647 bytes，62.144627 秒收到 Nginx HTML 504。
- 2026-07-14: 504 后 `/health` 的 API performance 未产生 completed preview sample；task 仍为 ready_for_import、hasImportedInvoices=false、importedInvoiceCount=0，确认没有误执行正式导入。
- 2026-07-14: CodeGraph 确认 `save_preview -> store_etc_import_archive -> _store_object_file -> write_verified_object`，每个 archive 顺序执行 2 PUT、2 GET、1 DELETE，并穿插 file-object pending/verified PostgreSQL 写入。
- 2026-07-14: boto3 官方 client 合同允许同一低层 client 在线程间共享；生产 PostgreSQL pool 默认最大 10，修复固定 4 个 writer。
- 2026-07-14: 新增回归先在旧串行实现上失败：最大 active writer 为 1；第 3 个任务失败后只清理前两个对象。实现后最大 active writer 大于 1 且不超过 4，失败场景清理其余全部成功对象。

## Eliminated

- 59 个 ZIP 损坏：全部内层 archive 通过完整性检查，且 SHA-256 均不同。
- 普通 ZIP/XML 解析是 60 秒主因：项目真实 parser 处理相同 bytes 低于 1 秒。
- 前端没有发送请求：直接 API smoke 已上传完整 multipart 并复现同一 Nginx 504。

## Resolution

- root_cause: 首轮修复消除了历史附件重复读取和 session 保存后的整批 reload，但 `PostgresEtcImportSessionStore.save_preview` 仍在 HTTP 请求内串行完成 59 个 archive 的 verified object write；真实解析仅 614ms，而每个 archive 的 MinIO temporary/final PUT+GET 与 PostgreSQL file-object 登记累计超过代理 60 秒。
- fix: 使用固定最多 4 个线程并发执行既有单文件 verified-write 合同，按原 ordinal 归位；等待全部 future 收敛后，只有全成功才单次保存 session，任一失败则清理所有已成功对象并禁止 repository commit。
- verification: 新增 bounded concurrency 与并发部分失败清理测试，连同 ETC service/API、session store、file-object storage 共 54 个目标测试通过；Ruff、docs check、scoped diff check 通过。真实 59 ZIP 生产 smoke 待本次 release 部署后完成。
- files_changed: `backend/src/fin_ops_platform/services/etc_import_session_store.py`、`tests/test_etc_import_session_store.py`、`docs/modules/imports-etc-invoices/{boundary-io.md,tests.md,implementation-notes.md}`。
