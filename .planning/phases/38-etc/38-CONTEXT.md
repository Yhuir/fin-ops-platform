# Phase 38：ETC 票据页面扁平化与流程可见性生产闭环

## 目标

在不改变 ETC 后端状态机、API response shape、权限、导入 worker、Workbench 投影和其它页面业务 I/O 的前提下，压平 ETC 票据页面的卡片层级，删除车牌与关键词筛选入口，并用现有批次、对账、导入和 OA 事实展示可信的四阶段生命周期摘要。

## 锁定决策

- 保留左侧批次列表、右侧批次工作面的主从结构；三 bucket 选择器归入批次列表头部。
- 删除页面级车牌和关键词输入、state、请求参数、依赖、测试、CSS 与文档描述；后端可选查询参数继续作为正式 API 合同保留。
- 四阶段按真实业务顺序显示：`准备核对资料 → 确认核对结果 → 导入 ETC 发票 → 提交 OA 审批`，不照搬 Figma 的错误顺序。
- 进度摘要只消费当前已加载的 business batch、reconciliation task、导入/发票事实；不新增 API、数据库字段、store、read model、worker、缓存或持久化 stage。
- `oa_confirmation_pending` 只表示等待人工确认；business batch submitted 不等于关联台 OA/流水/ETC 已配对。
- 失败、部分失败、回退、`not_submitted`、迁移冲突和非法组合必须 fail-safe，不能被压成绿色完成态。
- 页面保持现有 action handler、权限、删除确认、上传/解析、人工核对、reopen、导入入口、下载、OA 恢复/人工确认与 stale-request 防护。
- 使用现有 HeroUI、语义化 HTML 和 CSS；不新增第三方 stepper、动画或状态管理依赖。
- 视觉使用连续工作面、水平分隔和稳定间距；只给 dropzone、异常、表格与 dialog 保留完整边界。

## I/O 边界

### 输入

- `GET /api/etc/business-batches`：页面仅发送 bucket/page/page_size。
- `GET /api/etc/business-batches/{id}`：当前批次 detail。
- `GET /api/etc/reconciliation-tasks/{taskId}`：当前精确 task。
- Session 权限与现有 mutation handlers。

### 输出

- 四阶段只读展示投影、当前阶段说明、现有动作入口。
- 原有写 API、审计、对象存储、导入 worker 与 Workbench downstream 行为不变。

### 非目标

- 不废弃后端 plate/keyword API 参数。
- 不改 `/imports/etc-invoices` 的独立导入工作流。
- 不调整全局 App Shell、关联台、税金抵扣或成本统计页面。
- 不创建第二套 ETC 状态机或 page read model。

## 验收

- 新增第三方依赖、stepper 请求、timer、全局 listener 均为 0。
- 批次切换保持一个 detail 与一个精确 task 请求，并继续丢弃旧批次响应。
- 页面不存在车牌/关键词输入及其隐藏旧链路。
- 四阶段覆盖 draft/reviewing/ready/importing/imported/OA creating/pending/failed/not-submitted/submitted/closed 与异常组合。
- 桌面、窄屏、键盘、WCAG AA、loading/empty/error/permission 受测试保护。
- ETC 页面、独立导入页、Workbench ETC summary 及相关跨页回归通过；main 推送、部署和生产性能/链路验证闭环完成。
