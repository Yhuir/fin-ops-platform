---
quick_id: 260729-037
status: passed
verified_at: 2026-07-29
environment: production
---

# Quick Task 260729-037 Verification

## 合同

| 场景 | 结果 |
| --- | --- |
| ETC 搜索 summary | HTTP 200、fresh、6 groups；5 个折叠 group；`collapsed_rows` 泄漏 0 |
| ETC 单组 detail | HTTP 200；声明 34 张，返回 34 张 |
| 流水规则搜索 summary | HTTP 200、fresh；折叠 group 保留 bank count；`collapsed_rows` 泄漏 0 |
| 流水规则单组 detail | HTTP 200；声明 13 条，返回 13 条 |
| Workbench 页面 Audit | pass / integrity pass / freshness fresh / queue drained / issues 0 |

## 交互

- 搜索 ETC：默认显示“展开 34 张明细”；展开后显示“收起明细”；收起后恢复“展开 34 张明细”。
- 搜索流水规则：默认显示“展开 13 条明细”；展开和收起均成功。
- ETC 展开后直接切换到流水规则，再返回 ETC：恢复折叠，旧展开状态未残留。
- 清空搜索：ETC 34 张与流水规则 13 条批次仍默认折叠，均可展开再收起。
- 所有场景均未出现“加载失败”或“点击重试”。

## 性能

每项 warmup 2 次、采样 20 次，公网 gzip 登录态只读请求：

| 请求 | p50 | p95 | max | 目标 |
| --- | ---: | ---: | ---: | --- |
| ETC 搜索 summary | 238.2ms | 337.4ms | 373.2ms | p95 <= 1000ms |
| ETC group detail | 153.7ms | 177.2ms | 189.5ms | p95 <= 1000ms |
| 流水规则搜索 summary | 461.5ms | 549.1ms | 748.6ms | p95 <= 1000ms |
| 流水规则 group detail | 154.9ms | 185.0ms | 286.0ms | p95 <= 1000ms |

结论：合同、生产交互与既有性能目标全部通过。
