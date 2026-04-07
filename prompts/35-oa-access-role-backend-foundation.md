# Prompt 35：重构 OA 访问权限后端底座

## 目标

把当前 `fin-ops` 的 OA 权限模型从“单一可访问白名单”升级成三层口径：

1. 看得见并可访问 / 看不见且访问不了
2. 所有操作均可 / 只可看和只可导出
3. 只有 `YNSYLP005` 可管理权限

## 本次范围

- 重构后端访问控制模型
- 扩展 settings 持久化结构
- 扩展 `/api/session/me` 返回权限层级
- 不做前端设置页改版
- 不做完整按钮禁用联动

## 必须完成

1. 在 settings 中支持保存：
   - `allowed_usernames`
   - `readonly_export_usernames`
   - `admin_usernames`
2. 约束：
   - `readonly_export_usernames` 必须是 `allowed_usernames` 子集
   - `admin_usernames` 必须是 `allowed_usernames` 子集
   - 第一阶段管理员必须固定包含 `YNSYLP005`
3. `/api/session/me` 至少返回：
   - `allowed`
   - `access_tier`
   - `can_access_app`
   - `can_mutate_data`
   - `can_admin_access`
4. 保持现有 OA token 解析链路兼容
5. 补后端测试

## 验收标准

- 无访问资格账户：`allowed=false`
- 只读导出账户：
  - `can_access_app=true`
  - `can_mutate_data=false`
  - `can_admin_access=false`
- 全操作账户：
  - `can_access_app=true`
  - `can_mutate_data=true`
  - `can_admin_access=false`
- 管理员 `YNSYLP005`：
  - `can_access_app=true`
  - `can_mutate_data=true`
  - `can_admin_access=true`

## 实现提示

- 先写失败测试，再实现
- 优先修改：
  - `access_control_service.py`
  - `app_settings_service.py`
  - `state_store.py`
  - `auth.py`
  - `server.py`
