# 批量账务 Browser E2E Spec

日期：2026-08-05

## BA-E2E-001 页面 canonical 首屏

- 以有读取权限的 session 进入 `/batch-accounting`。
- 页面调用页面专属 GET，传入银行年份、bucket 和银行/OA 独立分页。
- 展示真实银行/OA rows、summary、pagination；响应和 UI 不出现 read-model freshness 状态。

## BA-E2E-002 加载、空集与错误

- 请求等待期间展示 loading。
- 成功空 rows 展示真实 empty。
- 失败展示后端 message，用户点击刷新后可以恢复。
- 错误不得被渲染为成功空集。

## BA-E2E-003 服务端 OA 搜索

- 输入 OA 搜索词后，请求携带 `oa_search` 并把 OA 页码重置为 1。
- 页面只展示服务端返回的匹配行。
- 不在浏览器全量 rows 上过滤或分页。

## BA-E2E-004 提交

- 用户选择一条银行流水和一个或多个 OA。
- 金额不一致时要求非空差额说明；匹配时无需说明。
- submit 成功后只执行一次当前页面 GET，不请求 operation barrier、不轮询。
- 重新 GET 后未提交数量下降、已提交数量上升。

## BA-E2E-005 已提交详情与撤回

- submitted bucket 展示 active batch relation 的 canonical 银行、OA 和发票成员。
- OA 详情只读，金额差异及说明可见。
- 撤回要求原因和 expected version。
- withdraw 成功后只执行一次当前页面 GET，关系返回未提交候选。

## BA-E2E-006 权限

- 读取权限允许查看页面。
- `read_export_only` 等无业务写权限 session 不显示或禁用 submit/withdraw，并且不得发出写请求。

## BA-E2E-007 页面韧性与布局

- 窄桌面视口的银行 rail、年份和分页不溢出。
- 双分页最大页大小 200，切页只请求目标页。
- 写成功而后置 GET 失败时，成功事实仍可见，并提示手动刷新。

## BA-E2E-008 标签规则与 canonical 联动

- 左栏每条批量账务流水在标题右侧显示当前银行明细 effective tag chip。
- 点击“批量账务标签规则”打开紧凑 HeroUI 右侧抽屉；每个实际出现的 active 标签有 checkbox。
- 取消标签并保存后，只重新请求当前列表一次；该标签流水从未提交左栏消失，summary/pagination 同步更新。
- 多选采用 OR；无标签、待分类/待确认、未勾选标签不进入未提交左栏；已提交 bucket 不受过滤。
- read-export 可查看规则但不能保存；直接 PUT 由后端拒绝。
