# 设置 状态机


> 修改 `设置` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。当前没有独立状态机时，在对应小节写明“不适用原因”，不要删除文件。

## 业务状态

- 当前状态：设置页包含普通 app settings、访问账户设置、数据重置，以及 `OA 申请人凭据管理`。
- 状态事实源：普通 app settings 仍来自 app settings service/state store；OA 申请人凭据来自独立 `app.oa_applicant_credentials` 表或本地内存 repository，不进入普通 settings payload。
- 允许流转：管理员保存目标 OA 申请人账号密码后，凭据状态从 `未配置` 变为 `已配置`；管理员删除/清空后回到 `未配置`。
- 禁止流转：非 admin 用户不能维护凭据；任何 API 响应、普通 settings payload、日志或前端状态都不能返回密码、密文或 OA token。

## UI 状态

- loading：设置页读取普通 settings 或凭据列表时展示加载态。
- empty：凭据列表为空或目标申请人未配置时显示 `未配置`。
- error：保存凭据失败、权限不足或后端配置缺失时显示接口错误。
- stale/refreshing：设置页本身不依赖 read model freshness。
- permission disabled/hidden：`OA申请人凭据` section 仅 admin 可见；全操作非 admin 不显示入口，也不能保存或删除凭据。
- credential form：密码只存在于当前表单输入中，保存成功后立即清空；列表只展示目标 OA 申请人、OA 登录账号和 `已配置`/`未配置`，不展示最近更新人、验证时间、密码、密文或 token。

## Read Model / Worker 状态

- fresh/missing/refreshing/stale/failed/unavailable：不适用，OA 申请人凭据不是 read model。
- refresh 触发来源：不适用。
- 失败恢复：保存/删除失败不改变既有凭据状态；PostgreSQL 模式保存/读取密码需要 `FIN_OPS_OA_APPLICANT_CREDENTIAL_KEY`。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| - | 初始骨架 | 待补充 | - |
| 2026-06-10 | 新增 OA 申请人凭据管理后端状态 | 设置页新增独立凭据事实源，admin-only，状态为 `已配置/未配置` | `tests.test_oa_applicant_credentials_service`、`tests.test_oa_applicant_credentials_api`、`tests.test_postgres_oa_applicant_credentials_repository`、`tests.test_postgres_migrations` |
| 2026-06-10 | 落地 OA申请人凭据设置页 UI | 管理员可在设置页维护目标申请人凭据；保存走独立凭据 API；普通 settings save 不包含密码 | `web/src/test/SettingsPage.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx` |
