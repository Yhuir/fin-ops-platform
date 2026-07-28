---
quick_id: 260728-ngb
title: 关联台逐栏折叠与搜索结果直显修复
must_haves:
  truths:
    - ETC 分组只折叠进项发票栏，OA 与银行栏按各自正常行合同校验，展开明细不再误报加载失败。
    - 流水规则批量处理只在银行栏超过既有阈值时折叠；普通关系和无 OA 银行批次全部直接显示。
    - 搜索命中折叠内容时显示真实匹配内容，不再显示“隐藏内容命中”，也不自动展开分组。
    - Workbench 继续使用 active generation read model，不新增 API、表、worker、缓存或兼容链路。
  artifacts:
    - web/src/features/workbench/api.ts
    - web/src/components/workbench/RelationGroupGrid.tsx
    - backend/src/fin_ops_platform/services/workbench_relation_grouping.py
    - backend/src/fin_ops_platform/services/postgres_repositories/read_models.py
    - backend/src/fin_ops_platform/services/workbench_read_model_version.py
  key_links:
    - 列表 projection 的 collapsed_row_counts 与详情 API 的 collapsed_rows 必须逐栏一致。
    - 前端只根据具体栏的 collapsed_row_counts/collapsed_rows 决定折叠和详情校验。
    - schema 版本升级使旧 generation 不会继续污染新显示合同。
---

# 目标

在不改变统一事实源、关系状态机和 Workbench active generation 架构的前提下，修正关联台的逐栏折叠合同，删除普通分组的旧折叠与占位搜索显示，并完成生产部署和只读验证。

# 任务

1. 以合同测试覆盖 ETC 逐栏详情校验、流水规则批次阈值、无 OA/普通分组直显和真实搜索命中预览。
2. 在现有 grouping、projection compaction、API mapper 和 RelationGroupGrid 边界内做最小根因修复，删除旧通用 preview、无 OA 折叠和“隐藏内容命中”逻辑。
3. 升级 Workbench display schema，更新受影响模块文档，执行针对性测试/构建，提交推送 main，部署并验证生产审计、功能和性能。

# 验收

- ETC 详情接口和前端校验按栏通过；不存在“加载失败，点击重试”。
- 普通多行和无 OA 银行批次不出现“还有 N 条，展开”。
- 只有 ETC 发票栏、银行流水规则批量处理银行栏（超过既有阈值）可以折叠。
- 搜索折叠内容时可看到真实命中行，分组保持折叠。
- Workbench audit 通过，active generation schema 为新版本，目标 API 热请求性能不退化。
