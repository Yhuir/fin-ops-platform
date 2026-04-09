# 关联台三栏列拖拽排序与持久化设计

日期：2026-04-08

## 目标

为 `已配对 / 未配对` 两个区域内的 `OA / 银行流水 / 进销项发票` 三栏增加：

- 列拖拽重排
- 列顺序持久化
- 下次登录自动恢复

同时保持：

- 表头 / 内容 / 底部滚动轨道始终对齐
- 三栏宽度缩放时，各列按相同比例拉伸
- 不影响现有搜索、筛选、排序和详情交互

## 交互原则

### 1. 同一 pane 共用一套列顺序

列顺序不是按 `已配对 / 未配对` 分两套保存，而是：

- `oa`
- `bank`
- `invoice`

每个 pane 一套顺序，两个区域共用。

### 2. 拖拽只改变顺序，不改变列宽

第一阶段只做：

- 拖拽重排列顺序
- 保存顺序

不同时做单列宽度拖拽，避免把交互复杂度和布局抖动一起放大。

### 3. 保存到关联台设置

列顺序作为 `workbench settings` 的一部分保存：

- 后端：`workbench_column_layouts`
- 前端：`workbenchColumnLayouts`

建议结构：

```json
{
  "oa": ["applicant", "projectName", "amount", "counterparty", "reason"],
  "bank": ["counterparty", "amount", "loanRepaymentDate", "note"],
  "invoice": ["sellerName", "buyerName", "issueDate", "amount", "grossAmount"]
}
```

## 实现边界

### 第一阶段

- 设置接口支持读写 `workbench_column_layouts`
- 前端按保存好的列顺序渲染
- 列拖拽 UI 可调整当前 pane 的顺序
- 保存设置时一起写回

### 第二阶段

- 拖拽完成后即时本地预览
- 增强拖拽手柄样式
- 键盘可访问性和移动端降级

## 技术方案

### 后端

- `app_settings_service.py`
  - 新增 `workbench_column_layouts` 规范化
  - 对缺失列自动补默认顺序
  - 忽略未知列 key
- `state_store.py`
  - 在 app settings 中持久化该字段
- `server.py`
  - `/api/workbench/settings` 读写此字段

### 前端

- `tableConfig.ts`
  - 继续维护 canonical default order
- `types.ts`
  - 新增 `WorkbenchColumnLayouts`
- `api.ts`
  - settings 映射与保存 payload 支持 column layouts
- `CandidateGroupGrid / WorkbenchRecordCard`
  - 改为按当前 pane layout 顺序渲染列
- 新增列拖拽状态与 helper

## 风险点

- 如果只改表头顺序，不改内容行和滚动轨道顺序，会再次出现竖线错位
- 如果允许保存不完整顺序，后续新增列可能消失

因此必须统一：

- 表头
- 记录行
- 底部滚动轨道

都使用同一份 column order。

## 验收标准

- 每个 pane 的列都可拖拽排序
- 保存后刷新页面仍保持顺序
- 下次登录仍保持顺序
- 未保存或空设置时回退默认顺序
- 表头 / 内容 / 轨道始终对齐
