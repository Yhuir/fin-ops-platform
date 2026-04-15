# 设置页页面化与树状两栏重构设计

日期：2026-04-14

## 目标

把当前“关联台设置”从弹窗改为独立页面 `/settings`，并把设置页整理成稳定的两栏树状结构，为后续 section 模块化拆分提供基础。

本轮设计拆为三步：

- `58`：路由与状态底座
- `59`：树状两栏与 section 拆分
- `60`：联调、测试与遗留清理

## 核心边界

### 1. 设置改为独立页面，不再由关联台弹窗承载

- 顶部 `设置` 按钮点击后进入 `/settings`
- 主导航新增 `设置`
- 关联台页不再持有“设置弹窗打开/关闭”状态
- 返回关联台、税金抵扣、成本统计均通过主导航完成

### 2. 保持现有业务语义，不在页面化时改动业务规则

页面化本身不改变以下业务能力：

- 项目状态管理
- 银行账户映射
- `保OA`
- `冲账规则`
- 访问账户管理
- 数据重置

即：先搬家，再拆组件，再清理。

### 3. 明确禁止改动 `form_data_db`

本组改动只涉及前端路由、页面承载和 settings API 的页面化接线。

禁止：

- 改动 `form_data_db`
- 写入、删除或迁移 `form_data_db.form_data`
- 借页面化之机顺手改 OA 源数据结构

## 当前问题

当前设置 UI 虽然内部已经有树状两栏雏形，但仍存在三个结构问题：

- 设置入口是 modal，不适合承载越来越多的配置分组
- 关联台页持有大量设置页状态、保存和危险动作逻辑，页面边界不清晰
- 组件过大，后续继续加设置项会快速失控

## 目标结构

### 路由层

- `/`：关联台
- `/tax-offset`：税金抵扣
- `/cost-statistics`：成本统计
- `/settings`：设置

### 页面层

- `SettingsPage`
  - 拉取 settings snapshot
  - 负责保存、项目同步、新增、删除、数据重置
  - 负责页面级 loading / error / success 状态
  - 不承担具体 section 渲染细节

### 组件层

后续拆分目标：

- `SettingsPageHeader`
- `SettingsTreeNav`
- `SettingsProjectsSection`
- `SettingsBankAccountsSection`
- `SettingsOaRetentionSection`
- `SettingsOaInvoiceOffsetSection`
- `SettingsAccessAccountsSection`
- `SettingsDataResetSection`

## 分阶段实施

### Prompt 58：路由与状态底座

范围：

- 新增 `/settings`
- 新增 `SettingsPage`
- 顶部 `设置` 按钮改为路由跳转
- 主导航加入 `设置`
- 设置相关加载/保存/项目同步/数据重置动作迁移到页面级容器
- 允许暂时复用现有设置编辑体，不要求本阶段完成 section 完整拆分

目标：

- “设置是页面”这件事先成立
- 关联台页不再持有设置弹窗状态

### Prompt 59：树状两栏与 section 模块化

范围：

- 把现有设置大组件拆成树导航和多个 section 子组件
- 设置页结构固定为左栏树、右栏内容
- UI 保持克制，不引入花哨卡片语言

目标：

- 降低组件复杂度
- 为后续扩展新增 section 打基础

### Prompt 60：联调、测试与遗留清理

范围：

- 清理关联台里残留的设置弹窗逻辑
- 路由 / 权限 / 保存 / 数据重置回归
- prompt 索引和相关文档更新

目标：

- 页面化迁移收口
- 自动化测试回到稳定状态

## 验收标准

- 点击顶部 `设置` 后进入 `/settings`
- `/settings` 可直接打开并正确加载设置
- 主导航中 `设置` 与当前页高亮一致
- 关联台不再弹出设置 modal
- 设置页保留现有主要业务分组和保存能力
- 所有实现明确禁止改动 `form_data_db`
