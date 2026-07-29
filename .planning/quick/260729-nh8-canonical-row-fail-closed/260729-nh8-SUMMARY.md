---
quick_id: 260729-nh8
status: completed
completed_at: 2026-07-29
commits:
  - bf429ea3e
---

# Quick Task 260729-nh8 Summary

## 结果

- `month=all` 关联预览现在把 active month generations 中内容完全相同的 canonical row 合并为一个逻辑 row。
- 同 row id 的金额、状态、来源或其它规范化字段不一致仍返回 `relation_preview_rows_ambiguous`，不会进入正式 relation UoW。
- selected row 顺序、OA attachment context、fresh/version 首尾门禁、20/100 行边界和正式写入 canonical reread 均保持不变。
- 前端为真实内容冲突增加稳定中文错误映射，不显示后端原始错误。

## 架构

- 修复位于 confirm/withdraw 共用的 `PostgresReadModelRepository` 行索引边界。
- 没有修改 projection、canonical relation facts、generation、SQL、schema、worker、queue、Redis 或 API shape。
- 没有使用 SQL `DISTINCT` 或 fallback 隐藏真实冲突。

## 发布

- 代码提交 `bf429ea3e` 已 push 到 remote `main`。
- 生产 release `main-bf429ea3-20260729170433` 已激活。

## 验证

- 真实“房克丽”选区从 409 恢复为 HTTP 200，`can_submit=true`，金额校验 matched，操作前 2 组、操作后 1 组。
- 生产只读 preview 20 次稳态采样 p50/p95/max 为 `252.383/730.272/814.141ms`。
- combined initial p50/p95 为 `208.458/303.235ms`；搜索未配对组 p50/p95 为 `156.195/175.834ms`。
- Page Audit 为 `pass / fresh / drained` 且 issues 为空；真实选区仍处于 unpaired，证明 preview 未产生业务写入。

详细测试分类、命令和残余风险见 `260729-nh8-VERIFICATION.md`。
