---
status: completed
created_at: 2026-06-21
completed_at: 2026-06-21
---

# OA 附件发票 Promotion 设置化与读路径收敛

## 目标

支持在设置页控制 OA 附件发票 promotion，避免用户手工清空发票池并重新导入 Excel 时，OA 附件 OCR 结果通过 OA 同步或关联台读路径重新写入 `app.invoices`。

## 方案

1. 新增设置 `oa_attachment_invoice_promotion_mode`：
   - `disabled`：完全不 promotion，不关联、不创建。
   - `link_existing_only`：只允许命中已有统一发票池记录时补 source link；不创建新发票。
   - `create_missing`：允许正式发票缺失时创建新 `app.invoices` 记录。
2. 默认值使用 `link_existing_only`，修正旧读路径默认自动建票的架构问题。
3. `_promote_oa_attachment_invoices_to_canonical(...)` 统一读取该设置；所有触发入口共用同一 gate。
4. 设置页展示三态选择，用户可在重新导入 Excel 前切换到 `disabled`。
5. 更新后端、前端测试和模块文档。

## 验收

- 设置 API 可 round-trip 新字段。
- 默认模式不会创建 OA 附件缺失发票，只会 link existing。
- `disabled` 模式不调用 `upsert_oa_attachment_invoice`。
- `create_missing` 模式保留受控创建能力。
- 设置页可见并可保存该开关。
