---
quick_id: 260729-dg6
status: completed
completed_at: 2026-07-29
commits:
  - 11947635f
  - 0c72cae27
---

# Quick Task 260729-dg6 Summary

## 结果

- ETC 票据管理的暂存、已提交批次在“发票明细”标题栏复用同一下载动作；服务端按批次成员稳定合并，一张发票一页。
- 历史 submitted 批次不再因缺少 OA 草稿 ID 被误拒绝。
- 增加管理员专用、CAS 版本保护的 submitted 批次附件恢复入口：只从原始 ZIP 补回 hash 完全一致的已有 PDF/XML，不创建发票、不改变批次成员、OA、配对或提交状态。
- ETC 创建 OA 时把已知内部 absolute 文件地址统一保存为 OA 根相对路径，未知 absolute host/path 继续 fail closed。
- 生产中 5 个缺失对象的历史批次已从原始 ZIP 恢复；7 个已提交批次全部可下载，页数分别为 64、34、44、27、43、1、36。
- 首次生产修复只覆盖 OA `6a0d63323bb8164165d8c614` 的 72 个错误内部附件引用；该单条结果不能代表历史 ETC OA 已全量修复。
- 后续全量读取 form 2 的 1,554 条 OA 记录，识别出 7 条 ETC OA；其中另有 4 条、344 个错误内部附件引用。4 条均经逐条备份、写前哈希一致性校验和精确字段替换完成修复，全表复扫后错误引用为 0。
- 用户报告的 3740.82 OA `6a5d77999bb648143aa7c2c6` 原有 128 个错误字段，对应 64 个唯一附件；修复后业务 payload 仅发生目标 URL 前缀替换，`processStatus=1`、金额和附件成员保持不变。
- 全部 7 条 ETC OA 中的 206 个唯一 PDF 引用均逐个验证为 HTTP 200/206、`application/pdf` 且文件头为 `%PDF-`。

## 数据安全

- 生产恢复前保存 7 个 business batch detail 和 OA record 原文、SHA-256。
- 批次恢复使用现有 invoice hash、submitted 状态、管理员权限和 expectedVersion 四重边界；生产幂等重放返回零修复且版本不变。
- OA 写入前重新读取并比对原始响应 hash；只允许精确前缀 `http://127.0.0.1:9300/fileManager/` 变为 `/fileManager/`。非 ETC 记录没有同类错误，未扩大写入范围。

## 发布

- `11947635f`：已提交批次 PDF UI/生命周期与 OA URL 归一。
- `0c72cae27`：历史附件受限恢复入口。
- `9fc854015`：记录首次生产验证证据；其单条 OA 验证结论已在本次全量复扫后纠正。
- 运行时修复代码已在生产 release `main-9fc85401-20260729105627` 中生效；历史 OA 数据通过受控生产修复直接收敛。

## 验证

详细命令、测试分类、生产页数、性能与残余风险见 `260729-dg6-VERIFICATION.md`。
