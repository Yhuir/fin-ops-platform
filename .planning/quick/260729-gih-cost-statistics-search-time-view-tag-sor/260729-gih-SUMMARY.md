---
status: complete
completed: 2026-07-29
description: 成本统计当前视图搜索、真实时间字段、标签排序、紧凑布局与自动分页
---

# Quick Task 260729-gih Summary

## Completed

- 保持成本统计 canonical API 直读，不新增 Redis、read model、worker、依赖或页面间 I/O。
- explorer 增加最长 200 字符的当前视图搜索；搜索在聚合、facets、summary 和 cursor 分页之前执行，规范化 query 绑定 cursor。
- `按时间` 改为真实银行对手方、银行标签、金额和流水摘要，不再展示伪造的“未配对OA / 未分类”。
- 主子标签按仅支出、混合、仅收入、零金额稳定排序，支出在收入上方，笔数使用独立方向颜色。
- 五个视图复用紧凑搜索框，使用 IME-safe debounce 和 stale request abort；三栏布局扩宽右侧明细并消除成本统计范围内的横向滚动。
- 删除手动“加载更多”按钮，表格内部接近底部时自动追加 cursor 下一页；失败保留已有 rows 并提供局部重试。
- 删除旧开发文档中的 Cost parent/shard read-model 合同，并同步产品、API、边界、状态机和测试事实源。

## Verification

- `python3 -m pytest -q tests/test_cost_statistics_policy.py tests/test_cost_statistics_api.py tests/test_cost_statistics_canonical_repository.py tests/test_platform_runtime_boundary_guards.py`：257 passed。
- `npm test -- --run src/test/CostStatisticsApi.test.ts src/test/CostStatisticsPage.test.tsx`：40 passed。
- `bash scripts/verify.sh lint`：通过。
- `npm run build`：通过；仅保留仓库既有 HeroUI 空 `:is()` 与主 chunk 大小警告。
- `git diff --check`：通过。

## Remaining Risk

- 生产 API 真实数据、query/cursor、Audit 和 p50/p95/max 在部署后执行并在任务交付中报告。
- 按用户要求未运行无关浏览器测试或全量 CI；UI 交互由成本统计定向组件测试和 production build 保护。
