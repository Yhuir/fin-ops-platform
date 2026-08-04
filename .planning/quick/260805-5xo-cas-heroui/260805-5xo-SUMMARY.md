---
quick_id: 260805-5xo
status: complete
date: 2026-08-05
---

# Quick Task 260805-5xo Summary

## 结果

- 日常报销批量账务未提交流水只按银行明细当前有效标签与显式已选标签准入；已提交与历史不受过滤。
- 左栏标题右侧显示当前 canonical 标签；页面右上角使用既有 `AppDrawer` 与 HeroUI `Button`、`Checkbox`、`Chip` 提供紧凑规则抽屉。
- 规则写入复用 Settings owner，包含 stable code、版本、CAS、semantic no-op 和审计；只看/只导出用户只能读取。
- 提交时在同一 canonical 查询边界重新验证规则版本、当前标签及准入资格，防止陈旧页面提交已经失效的流水。
- 删除旧 `_unsubmitted_bank_rows` 查询入口；没有新增 read model、worker、queue、cache、fallback、依赖或客户端全量过滤。

## 变更边界

- Settings：`AppSettingsService`、PostgreSQL settings repository/state-store adapter、migration `0135`。
- Batch Accounting：route、service、canonical query repository、API DTO 与页面。
- Bank Details：只复用现有 effective-category classifier，新增 bounded projection helper，不改变标签事实源。
- 文档与测试：模块边界、API、业务流程、权限清单、前后端与 Browser E2E。

## 验证

- 后端目标矩阵：400 passed，3 skipped。
- 前端目标矩阵：23 passed。
- 后端全量：3904 passed，55 skipped；skip 均为本机没有 disposable PostgreSQL 的既有集成条件。
- 前端全量：74 files，946 passed，production build 通过。
- Chromium E2E：170 passed。
- `bash scripts/verify.sh lint`、`bash scripts/verify.sh docs`、`git diff --check` 全部通过。
- 旧生产同路径基线（20 次、并发 4）：200 成功 20/20，p50 761.770ms，p95 992.462ms，p99 1048.983ms。

## 七类测试评估

- 业务核心单元测试：覆盖默认选择、稳定 code、输入校验、版本冲突、semantic no-op 与规则归档。
- 服务层测试：覆盖 canonical 标签过滤、固定查询预算、设置持久化/审计和提交时重校验。
- API 合同测试：覆盖 GET/PUT、403、409、503、响应 shape 与 session actor 防伪造。
- read model/cache/worker：不适用；本轮明确不新增或恢复这些链路，静态边界门禁防止回归。
- 前端组件与交互：覆盖抽屉 loading/empty/error/readonly/save、标签显示、保存后刷新和冲突反馈。
- 端到端业务流：覆盖规则选择过滤左栏及既有提交/撤回链路。
- 既有功能回归：全量后端、前端、Browser E2E 通过；已提交 bucket 与未观察但仍有效的已选 code 均受保护。

生产 active SHA、migration、真实规则/list 合同和部署后性能证据由同一任务的标准 deploy-control 与最终交付报告承载，避免把环境瞬时状态写成长期代码事实。
