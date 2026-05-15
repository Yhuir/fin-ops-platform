# Prompt 52：设置页数据重置联调、QA 与文档收口

目标：完成三类数据重置工具的联调与回归，确保删表范围、权限边界和 OA 重刷行为符合设计。

前提：

- 阅读：
  - `docs/superpowers/specs/2026-04-14-settings-data-reset-tools-design.md`
  - `docs/superpowers/plans/2026-04-14-settings-data-reset-tools.md`

要求：

- 明确验证整个实现过程中没有任何动作会修改或删除 `form_data_db.form_data`
- 验证 `清银行流水` 的删表范围正确
- 验证 `清发票` 的删表范围正确
- 验证 `清 OA 并重新写入` 固定采用模式 B
- 验证 OA 重刷按 `oa_retention.cutoff_date` 生效
- 验证：
  - 管理员可见
  - 普通全量账号不可见
  - 只读导出账号不可见
- 验证三个危险按钮执行前都要求当前 OA 用户密码复核
- 验证未输入 / 输错 OA 密码时不会执行清理、缓存失效或 OA 重建
- 验证审计日志、错误日志和 API 响应中不包含 OA 密码
- 更新 README、需求文档和 prompt 索引

建议文件：

- `README.md`
- `prompts/README.md`
- `docs/product/银企核销需求.md`
- `tests/test_workbench_v2_api.py`
- `tests/test_settings_data_reset_service.py`
- `web/src/test/WorkbenchSelection.test.tsx`

交付要求：

- 三类动作的边界有自动化测试覆盖
- 当前 OA 用户密码复核有前后端测试覆盖
- 文档和 prompt 索引同步更新
- 明确记录“只清应用库，不清 OA 源库”

验证：

- 跑相关后端测试
- 跑相关前端测试
- 跑前端 build
