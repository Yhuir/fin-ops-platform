# Settings Data Reset Tools Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 在关联台设置页新增三类高风险数据管理工具，支持按域清理 app 数据，并支持按 `保OA` 日期执行模式 B 的 OA 彻底重刷。

**Architecture:** 新增独立管理动作 service 负责按固定集合组执行清理；前端设置页只展示危险操作入口与反馈，并在每个危险动作执行前弹出当前 OA 用户密码输入；后端必须校验该密码属于当前 OA 会话用户，通过后才执行清理。OA 重刷不碰源库，只失效 app 侧缓存、pair relation、override 和 read model 后再重建。

**Tech Stack:** Python backend、Mongo state store、现有 AppSettingsService / WorkbenchSettingsModal / MongoOAAdapter、React 前端设置弹窗、unittest + Vitest。

---

## File Map

### Backend

- Create: `backend/src/fin_ops_platform/services/settings_data_reset_service.py`
- Modify: `backend/src/fin_ops_platform/services/state_store.py`
- Modify: `backend/src/fin_ops_platform/services/app_settings_service.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Create or modify: `tests/test_settings_data_reset_service.py`
- Create or modify: `tests/test_app_settings_service.py`
- Create or modify: `tests/test_workbench_v2_api.py`

### Frontend

- Modify: `web/src/components/workbench/WorkbenchSettingsModal.tsx`
- Modify: `web/src/features/workbench/api.ts`
- Modify: `web/src/features/workbench/types.ts`
- Create or modify: `web/src/test/WorkbenchSelection.test.tsx`

### Docs

- Modify: `docs/product/银企核销需求.md`
- Create: `docs/superpowers/specs/2026-04-14-settings-data-reset-tools-design.md`
- Create: `docs/superpowers/plans/2026-04-14-settings-data-reset-tools.md`
- Modify: `prompts/README.md`
- Modify: `README.md`

---

## Task 1: 建立后端数据重置边界

- [ ] 写失败测试：三类 reset action 只能操作固定白名单集合
- [ ] 写失败测试：未提供或提供错误的当前 OA 用户密码时，reset action 不执行任何清理
- [ ] 新增 `SettingsDataResetService`
- [ ] 明确定义三类动作：
  - `reset_bank_transactions`
  - `reset_invoices`
  - `reset_oa_and_rebuild`
- [ ] 固定禁止操作：
  - `form_data_db.form_data`
  - `app_settings`
  - 所有 `*_meta`
- [ ] reset API 接收一次性的 `oa_password`，只绑定当前 OA session 用户校验，不允许客户端传入或切换用户名
- [ ] 确保 `oa_password` 不落库、不写日志、不出现在响应或异常堆栈中
- [ ] 跑针对性后端测试

## Task 2: 落地集合组清理逻辑

- [ ] 写失败测试：清银行流水会联动删匹配结果 / pair relation / read model
- [ ] 写失败测试：清发票会联动删税金认证记录与相关状态
- [ ] 写失败测试：清 OA 固定采用模式 B，会清 `oa_attachment_invoice_cache + workbench_read_models + workbench_pair_relations + workbench_row_overrides`
- [ ] 在 `state_store.py` 增加按域清理能力，避免前端或 server 直接散落删库逻辑
- [ ] 返回删除摘要与影响统计
- [ ] 跑针对性后端测试

## Task 3: 接通 OA 重刷

- [ ] 写失败测试：`reset_oa_and_rebuild` 会读取 `oa_retention.cutoff_date`
- [ ] 清理后触发 OA 缓存失效与重建
- [ ] 重新生成 OA 附件发票缓存和 workbench read model
- [ ] 失败时返回“已清理 / 重建失败”的明确状态
- [ ] 跑针对性后端测试

## Task 4: 设置页危险操作 UI

- [ ] 写失败测试：仅管理员可见 `数据重置` 分组
- [ ] 写失败测试：点击任一清理按钮后必须完成二次确认和当前 OA 用户密码输入，取消或输错时不调用清理成功路径
- [ ] 在设置树中新增 `数据重置`
- [ ] 增加三个危险按钮与说明文案
- [ ] 增加二次确认和执行中状态
- [ ] 二次确认后弹出密码输入框，文案提示“请输入当前 OA 用户密码以确认本次高风险操作”
- [ ] 前端不保存、不打印、不展示密码；点击取消立即关闭并不执行动作
- [ ] 动作成功后刷新设置页和相关页面状态
- [ ] 跑针对性前端测试

## Task 5: 联调、QA 与文档收口

- [ ] 验证清银行流水 / 清发票 / 清 OA 的删表范围符合设计
- [ ] 验证 `清 OA` 按 `保OA` 日期重建
- [ ] 验证普通账号与只读导出账号不可见
- [ ] 验证未输入 / 输错当前 OA 用户密码时不会清任何集合，也不会触发 OA 重建
- [ ] 验证审计日志、错误日志和 API 响应不包含 OA 密码
- [ ] 更新 README 与 prompts 索引
- [ ] 跑后端全量相关 tests
- [ ] 跑前端相关 tests
- [ ] 跑前端 build
