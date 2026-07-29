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
- OA `6a0d63323bb8164165d8c614` 的 72 个错误内部附件引用已精确替换；其它业务 payload 与 `processStatus=1` 保持不变，36 个唯一附件均验证为可访问 PDF。

## 数据安全

- 生产恢复前保存 7 个 business batch detail 和 OA record 原文、SHA-256。
- 批次恢复使用现有 invoice hash、submitted 状态、管理员权限和 expectedVersion 四重边界；生产幂等重放返回零修复且版本不变。
- OA 写入前重新读取并比对原始响应 hash；只允许 72 个已知 URL 字段发生变化。

## 发布

- `11947635f`：已提交批次 PDF UI/生命周期与 OA URL 归一。
- `0c72cae27`：历史附件受限恢复入口。
- 生产 release：`main-0c72cae2-20260729103135`。

## 验证

详细命令、测试分类、生产页数、性能与残余风险见 `260729-dg6-VERIFICATION.md`。
