# 数据安全与重置模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：partial
- 当前边界可信度：high
- 目标边界：所有数据重置通过 SettingsDataResetService 和 background job 执行，必须可审计、可阻断误用、可验证。
- 当前缺口：重置会影响所有 read model/worker，变更必须同步 operations 文档。
- 旧代码删除条件：旧 reset script/API 不再绕过 service。

## 职责边界

### 负责

- 设置页数据重置、reset job、进度查询和安全防护。
- 重置后触发 derived lifecycle/read model rebuild。
- 运维脚本和生产安全约束。

### 不负责

- 不承载普通业务写操作。
- 不直接绕过 service 清理生产数据。
- 不在前端保存 reset secret 或跳过权限。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| Reset request | Settings page/API | 必须权限校验和确认 |
| Reset job poll | frontend/app health | 只读 job 状态 |
| Script invocation | `scripts/reset_demo_db.sh` | 仅符合运维边界 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| Reset job | background job service | 可追踪、可失败恢复 |
| Lifecycle event | derived data lifecycle | `settings_reset_completed` 等显式事件 |
| Read model invalidation | runtime queue/app status | 不留下伪 fresh |

## 持久化与投影

- Own read model：无。
- 影响 read model：全部或大部分 read model。
- Service owner：`SettingsDataResetService`。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Backend service | `backend/src/fin_ops_platform/services/settings_data_reset_service.py` |
| Backend route | data reset endpoints in `backend/src/fin_ops_platform/app/server.py` |
| Job | `BackgroundJobService`、`settings_data_reset` |
| Lifecycle | `derived_data_lifecycle_service.py` |
| Frontend | `web/src/pages/SettingsPage.tsx`、`web/src/components/workbench/SettingsDataResetDialogs.tsx` |
| Operations | `scripts/reset_demo_db.sh`、`docs/operations/data-safety.md` |
| Tests | `tests/test_settings_data_reset_service.py`、`web/e2e/settings-data-reset-flow.spec.ts` |

## 依赖方向

- 允许依赖：background job service, lifecycle service, app status。
- 必须通过：SettingsDataResetService。
- 禁止绕过：直接数据库清理；绕过权限/审计执行 reset。

## 测试与验证

- `tests/test_settings_data_reset_service.py`
- `web/e2e/settings-data-reset-flow.spec.ts`

## 当前缺口和删除条件

- 生产数据操作必须同步 operations 文档和回滚/备份策略。
