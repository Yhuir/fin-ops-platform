# Prompt 51：设置页危险操作 UI 与 OA 模式 B 重刷

目标：把数据重置工具接入现有 `关联台设置` 弹窗，并完成 `清 OA` 的模式 B 重刷联动。

前提：

- 阅读：
  - `docs/superpowers/specs/2026-04-14-settings-data-reset-tools-design.md`
  - `docs/superpowers/plans/2026-04-14-settings-data-reset-tools.md`

要求：

- 在设置树中新增 `数据重置` 分组
- 仅管理员可见
- 明确禁止触碰：
  - `form_data_db.form_data`
- 增加三个按钮：
  - `清除所有银行流水数据`
  - `清除所有发票（进销）数据`
  - `清除所有 OA 数据并重新写入`
- 每个按钮都要有：
  - 危险说明
  - 二次确认
  - 当前 OA 用户密码输入弹窗
  - 执行中状态
  - 成功 / 失败反馈
- 确认流程必须是：点击危险按钮 -> 展示影响范围并二次确认 -> 弹出当前 OA 用户密码输入 -> 调用后端 reset API
- 密码弹窗不能允许切换用户名，只能提示输入当前登录 OA 账户的 OA 系统密码
- 前端不保存、不打印、不回显 OA 密码；取消或后端校验失败时，不进入成功状态，也不刷新成“已清理”
- `清 OA` 固定采用模式 B：
  - 清 `oa_attachment_invoice_cache`
  - 清 `workbench_read_models`
  - 清 `workbench_pair_relations`
  - 清 `workbench_row_overrides`
  - 再按 `保OA` 日期重建

建议文件：

- `web/src/components/workbench/WorkbenchSettingsModal.tsx`
- `web/src/features/workbench/api.ts`
- `web/src/features/workbench/types.ts`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_settings_data_reset_service.py`
- `web/src/test/WorkbenchSelection.test.tsx`

交付要求：

- UI 风格延续当前树状两栏设置页
- 不出现普通账号可见危险按钮
- 三个危险按钮都必须经过当前 OA 用户密码复核
- `清 OA` 成功后相关页面能回到重建后的状态

验证：

- 增加前端交互测试
- 覆盖取消密码输入、密码错误返回时不展示成功反馈
- 跑相关前端 / 后端测试
