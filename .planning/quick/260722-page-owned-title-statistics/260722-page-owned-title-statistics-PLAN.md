# 页面自有全量标题统计实施计划

日期：2026-07-22

## 目标

为银行明细、OA 待付款核对、外部往来款管理、ETC 票据管理、税金抵扣、待找发票、进项发票使用情况、销项发票收款情况、关联台和成本统计提供同标题行的全期间笔数统计。统计只来自目标页面自己的主查询、read model 或 direct-canonical 页面边界；App Health Page Audit 继续独立读取 canonical facts 做完整性对照。

## 不变量

- 标题统计不受月份、搜索、筛选、排序、分页影响。
- 不增加浏览器请求，不新增跨页 API、统一统计服务、表或 worker。
- 页面统计不能从 Page Audit 或统一事实源回填；Audit 不能进入页面热路径。
- 只有页面投影的全期间 freshness 可证明时返回数字；missing/refreshing/stale/schema mismatch 返回不可用，合法空集返回 `0`。
- 所有有页面访问权限的用户可见；Page Audit 权限不变。
- 数量按业务身份去重，折叠组不能把表格行数冒充 OA、流水或发票数量。

## I/O 边界

```text
page-owned canonical/projection input
  -> existing projector/repository aggregate
  -> existing page main API response.statistics + statistics_status
  -> pure PageStatisticsPopover title accessory

independent canonical facts
  -> existing Page Audit executor
  -> admin-only audit result
```

## 实施波次

1. 共享 UI：实现纯 props 的紧凑标题统计与明细 Popover；完整数字、千分位、零值、不可用和 loading 均有明确表现。
2. 页面数据：在 10 个现有主响应中增加模块私有 `statistics` / `statistics_status`；聚合复用已有投影发布或现有 SQL transaction。
3. Freshness：全期间 child scopes 任一 dirty/missing/schema 不匹配时，不暴露统计数字；缓存和 ETag 绑定全期间统计版本。
4. 前端接入：只消费当前页面主响应；删除进项/销项旧 `page_size=1` 标题二次请求和其死状态/测试。
5. Audit：复用现有页面审计器独立证明 canonical expected set、投影成员、关系边与全期间统计输入一致；不创建另一套审计系统。
6. 测试与性能：覆盖业务口径、repository/service、API、read model/cache/worker、组件交互、关键跨模块刷新和旧页面回归；对新增聚合执行查询形状/EXPLAIN 与页面请求耗时验证。
7. 文档与生产：更新受影响模块 boundary I/O、tests/implementation notes 和 API/read-model 长期事实；通过正式发布入口部署，刷新相关 scopes，等待 durable queue drain，验证统计恒等式、筛选稳定性、fresh Audit 和回滚点。

## 验收标准

- 10 个页面均在标题同行显示核心统计，Popover 显示补充统计。
- 所有数字使用完整十进制和千分位，不使用“万”缩写，不显示金额。
- 页面切换筛选/月/分页时，统计对象逐字段不变且无额外网络请求。
- 统计恒等式成立：例如流水=支出+收入；银行流水=已分类+未分类=已关联+未关联；对应模块的组/补集恒等式成立。
- 生产主响应 `statistics_status=fresh`，Page Audit freshness/integrity/queue 均通过；若外部控制证据仍未知，明确区分为 App 注册前的外部边界。
- 相关全量验证零失败；未执行的环境门禁和剩余风险明确记录。

## 回滚

- 代码回滚到部署前 active release；无 schema destructive migration、无业务事实写入。
- 若统计聚合造成请求性能回退，可先回滚 UI/API 字段而不影响原列表、写操作或 read model 数据。
- 生产刷新只通过既有 `ReadModelRefreshGateway` / durable queue；不手工写 fresh readiness 或 read model 表。

## 实施结果（2026-07-22）

- 已在 10 个既有页面主响应中增加页面自有、全期间、fresh-gated 的 `statistics` / `statistics_status`，前端统一使用轻量 HeroUI Popover 展示。
- 已删除进项/销项标题统计的旧 `page_size=1` 二次请求及相关状态；没有新增浏览器请求、跨页统计服务、表或 worker。
- 已将统计版本纳入相关 read model/source-version/cache 合同；missing、dirty、schema/source-version mismatch 时不暴露旧数字。
- 已扩展独立 Page Audit，以 canonical facts 对照页面投影统计；Audit 仍不进入普通页面热路径。
- 专项后端回归通过 677 个测试；前端 74 个文件、876 个测试全部通过；生产构建、lint、docs 与 diff 校验通过。
- 全量后端 4,271 个测试中仅保留 5 个已在变更前 HEAD 复现的基线失败（3 个 no-OA/workbench fixture、1 个 bank-flow contract harness、1 个 write-operation cost fanout matrix），本次新增 architecture guard 已修复并通过。
- 生产发布、scope 刷新、Page Audit 与请求耗时证据在代码提交后执行并补充到最终交付说明。
