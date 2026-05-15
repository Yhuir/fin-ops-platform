# Prompt 59：设置页 section 拆分与树状两栏 UI

目标：把页面化后的设置页拆成左栏树导航和右栏 section 组件，形成清晰、可扩展的两栏树状结构。

前提：

- 阅读：
  - `docs/superpowers/specs/2026-04-14-settings-page-route-and-tree-design.md`
  - `docs/superpowers/plans/2026-04-14-settings-page-route-and-tree.md`
- 已完成：
  - `58-settings-page-route-and-state-foundation.md`

要求：

- 抽出 `SettingsTreeNav`
- 抽出 `SettingsPageHeader`
- 拆分以下 section 组件：
  - 项目状态
  - 银行账户
  - 保OA
  - 冲账规则
  - 访问账户
  - 数据重置
- 保持树状两栏、简洁克制的 UI
- 不改现有 settings API 语义

建议文件：

- `web/src/pages/SettingsPage.tsx`
- `web/src/components/settings/SettingsTreeNav.tsx`
- `web/src/components/settings/SettingsPageHeader.tsx`
- `web/src/components/settings/SettingsProjectsSection.tsx`
- `web/src/components/settings/SettingsBankAccountsSection.tsx`
- `web/src/components/settings/SettingsOaRetentionSection.tsx`
- `web/src/components/settings/SettingsOaInvoiceOffsetSection.tsx`
- `web/src/components/settings/SettingsAccessAccountsSection.tsx`
- `web/src/components/settings/SettingsDataResetSection.tsx`
- `web/src/app/styles.css`

验证：

- 跑设置页相关前端测试
- 跑前端 build

禁止项：

- 不要改动 `form_data_db`
- 不要写入、删除或迁移 `form_data_db.form_data`
- 不要重做设置业务规则
- 不要顺手扩 scope 到新的设置功能
