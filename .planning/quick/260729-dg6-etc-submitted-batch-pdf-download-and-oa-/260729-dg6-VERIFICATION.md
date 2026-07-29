---
quick_id: 260729-dg6
status: passed
verified_at: 2026-07-29
---

# Quick Task 260729-dg6 Verification

## 本地门禁

- `bash scripts/verify.sh lint`：通过。
- `bash scripts/verify.sh docs`：通过。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_etc_invoice_pdf_bundle_service tests.test_etc_backend`：145 tests passed，4 个既有显式 skip。
- ETC PDF/OA URL 针对性后端集合：143 tests passed，4 个既有显式 skip。
- ETC 页面组件：72 tests passed。
- ETC API mapper：20 tests passed。
- `cd web && npm run build`：通过；只有既有 HeroUI CSS minify 与 chunk-size warning。
- `git diff --check`：通过。
- 后端全量曾运行 3786 tests；唯一失败是 origin/main 已存在的成本统计文档覆盖编号缺失，与本任务无关且未扩大范围修复。

## 七类测试评估

1. Business core unit：适用；覆盖批次资格、稳定排序、单票单页、hash 校验、缺件、损坏、非单页、大小边界和恢复 hash 不一致。
2. Service layer：适用；覆盖附件恢复、版本递增、审计、幂等重放、零写入失败分支。
3. API contract：适用；覆盖 PDF headers/error、admin 权限、multipart、expectedVersion 和恢复后下载。
4. Read model/cache/background job：不适用；该页面和恢复入口直接读取/修复 canonical ETC batch/invoice facts，不新增或改变 read model、cache、queue、worker。
5. Frontend interaction：适用；覆盖暂存/已提交标题栏下载、loading/error、下载不触发展开折叠。
6. End-to-end business flow：适用；本地覆盖 submitted batch -> attachment repair -> merged PDF，生产覆盖原始 ZIP -> 恢复 -> 7 批 PDF -> OA 36 附件。
7. Existing feature regression：适用；覆盖 ETC business batch、OA client、原导入/提交/删除和页面交互既有测试。

## 生产验证

- release `main-0c72cae2-20260729103135` 激活；后端、前端、RabbitMQ dispatcher 和 11 个 runtime worker 为 active，readiness 通过。
- submitted list 7 条；恢复结果：
  - `etc_business_batch_0004`：35 PDF + 35 XML，1 条原本可用，幂等重放 0 写入。
  - `hist_20260413_241125`：44 PDF + 44 XML。
  - `hist_20260312_193545`：27 PDF + 27 XML。
  - `hist_20260215_154900`：43 PDF + 43 XML。
  - `hist_20260114_187293`：1 PDF + 1 XML。
- 7/7 合并 PDF 为 HTTP 200 `application/pdf`，header count 与 `pdfinfo` 页数严格一致：64、34、44、27、43、1、36。
- 1673.30 批次首尾页已渲染检查，均为正常单页电子通行费发票。
- 首次验证只修复并验证了 OA `6a0d63323bb8164165d8c614` 的 72 个附件 URL 和 36 个唯一附件；该证据不足以证明全部历史 ETC OA，不能作为全量通过结论。
- 纠正验证读取 form 2 全部 1,554 条记录：共 7 条 ETC OA，另发现 4 条受影响记录、344 个错误字段，非 ETC 同类错误为 0。
- 4 条受影响记录逐条保存原文与 SHA-256；每次 PUT 前重新读取并比较 canonical record hash，只把 `http://127.0.0.1:9300/fileManager/` 替换为 `/fileManager/`。
- 纠正后的全表复扫结果：1,554/1,554 加载完成，7 条 ETC OA 的错误引用为 0，非 ETC 错误引用为 0。
- OA `6a5d77999bb648143aa7c2c6`（3740.82）由 128 个错误字段收敛为 0，64 个唯一附件路径均为根相对引用；`processStatus=1`、金额、创建信息和附件成员不变。
- 7 条 ETC OA 共 206 个唯一 PDF 引用逐一返回 HTTP 200/206、`application/pdf` 且 magic 为 `%PDF-`；用户报告的 `26537912210500678556_20260720091917A130.pdf` 包含在通过集合中。

## 性能

- readiness：497.5 ms。
- submitted list：149.1 ms。
- 36 张 batch detail：223.3 ms。
- OA record：103.6 ms。
- 36 页 PDF：0.89–2.57 s（多次公网样本）。
- 64 页 PDF：2.48–3.28 s warm，多一次 cold 样本 4.99 s。
- 36 个 OA PDF 并发 8 路探测：5 s 全部完成。
- 206 个唯一 ETC OA PDF 并发 8 路探测：4.8 s 全部完成。

## 残余风险

- PDF 合并当前按需从对象存储读取并实时合并；大批次耗时与页数/对象存储延迟线性相关。本任务没有引入 Redis、预生成文件或后台 worker，避免第二份 PDF 事实和失效复杂度。
- 未运行浏览器 E2E 或无关 CI；用户已明确要求避免无意义浏览器测试和 CI，本次以组件、API、生产真实 PDF/OA 链路替代。
- 旧的完整 malformed URL 即使被手工粘贴仍然无效；有效链接必须来自修复后的 OA 记录并解析为 `/oa-api/fileManager/...`。本次通过全表复扫证明 OA 当前数据不再返回旧前缀。
