---
quick_id: 260728-g9q
status: completed
completed_at: 2026-07-28
commit: PENDING
---

# Quick Task 260728-g9q Summary

## 结果

- OA canonical row 自身明确携带的 Mongo 文档 ID、流程 ID、request ID 等来源别名统一通过共享 alias map 归一到 canonical OA ID。
- 当前窗口和历史窗口的正式匹配均使用同一确定性映射；别名冲突 fail closed，不使用金额、申请人、项目名或顺序猜测。
- OA 附件发票的父 OA 与付款项 `row_index` 作为精确绑定写入正式关系 metadata，扩展和撤回时保持不可拆散。
- 页面只在显示边界把来源付款项 ID 映射为 canonical expense item ID；canonical 发票事实继续保留原始来源证据。
- matching 规则版本已升级，发布后由正式 `workbench-matching` worker 按 source-version 合同重算旧 scope。

## 复用与删除

- 复用既有 `oa_attachment_invoice_linking`、正式 relation UoW、matching dirty scope 和 Workbench generation 边界。
- 未新增表、worker、read model、兼容旁路或模糊匹配。
- 删除各调用点自行解释来源 ID 的隐式假设，统一收口到共享 alias map 与 exact binding metadata。

## 验证

- 相关业务核心、repository、matching、relation command、withdraw/alignment/grouping：117 tests passed。
- 相邻 matching orchestrator、OA attachment context、Workbench query/SQL projection：32 tests passed。
- `bash scripts/verify.sh lint`：passed。
- `bash scripts/verify.sh docs`：passed。
- `git diff --check`：passed。

## 发布

提交、推送、正式部署和生产只读收敛验证由主控在同一任务中继续执行。
