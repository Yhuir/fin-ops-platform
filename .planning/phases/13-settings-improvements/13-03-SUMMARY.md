---
phase: 13-settings-improvements
plan: "03"
status: complete
completed: 2026-08-02
requirements:
  - PAGE-15
  - PAGE-04
  - PAR-01
  - PAR-02
  - PAR-03
---

# 13-03 执行摘要

## 完成结果

- Web generic `WorkbenchSettings`、mapper 与 serializer 不再包含任何 ACL 字段；普通设置、关联台列顺序保存继续使用原 `/api/workbench/settings`，body 中无 ACL。
- 新增专用 ACL wire/domain type 与 `GET/PUT /api/workbench/settings/access-control` client；PUT body 只有 `expected_version` 与 `accounts`。
- SettingsPage 仅在 active admin session 加载 ACL，并维护独立 loading/saving/error/conflict 状态；409 保留当前编辑，不静默覆盖。
- 访问账户区只编辑 `full_access` / `read_export_only`，`YNSYLP005` 只读展示且不能添加、改级或删除；ACL 使用独立保存按钮。
- 完整删除 `WorkbenchSettingsModal` 的第二套 ACL UI、state、helper、props 与导航入口。
- unit/E2E mock 与生产合同对齐：generic ACL key 明确 400，dedicated 非 admin 403，admin PUT 执行 version CAS；无兼容 mapper 或 fallback。

## 验证

- targeted Vitest：96 tests passed；新增 SettingsPage admin-only load/save、protected admin、409 draft preservation 与 generic body absence 断言。
- `bash scripts/verify.sh frontend`：73 test files / 904 tests 全部通过，production build 通过。
- `npx playwright test e2e/permissions-role-matrix.spec.ts --project=chromium`：7/7 通过；覆盖 full-access 直接 generic/dedicated API 提权失败、admin 专用修改成功、新 session 变为 read-export，以及 AppHealth/OA credential/data reset 回归。
- frontend legacy sentinel：旧 ACL 字符串只保留在拒绝/攻击测试；runtime serializer、generic fixtures 与 Workbench modal 无命中。
- `git diff --check`：通过。

## 性能与边界

- 非 admin 不发 ACL GET；admin 只在设置页 active 时并行发一次窄 GET，离页或降权立即 abort/清理。
- ACL 与普通 settings 保存互不串联，不新增状态库、依赖、worker、cache、read model 或跨页面 I/O。

## 后续

- Wave 3 更新长期模块/API/运维事实源并执行全量 docs、lint、backend、frontend、E2E 与部署预检。
