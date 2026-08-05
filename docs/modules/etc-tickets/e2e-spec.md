# ETC票据管理 Spec-first E2E Spec

本文件定义 `/etc-tickets` 页面在真实浏览器中的业务验收合同。测试必须保护 ETC 业务批次、发票明细、OA 草稿、人工提交、删除/reset、source file、Workbench summary fan-out、read model/worker 边界和权限，而不是保护当前组件实现细节。

## 模块目标

ETC 票据管理页面以 `/api/etc/business-batches*` 和 `etc_business_batches` 为用户可见事实源。`etc_reconciliation_tasks` 只作为导入、核对、source file 和 workflow 状态。页面不能把 task-only 记录当成批次展示，也不能用本地事件伪造 OA 已提交、Workbench summary 已 fresh 或下游页面已收敛。

## 用户角色

- `admin`：可读取、创建批次、上传 source file、创建 OA 草稿、人工确认、删除/reset 和查看运维入口。
- `full_access`：可执行 ETC 业务批次日常写操作和读取批次状态。
- `read_export_only`：可读取允许的 ETC 批次视图，不得创建草稿、确认提交、上传 source file、删除/reset 或触发 import mutation。
- forbidden/expired session：不能进入受保护页面或调用受保护 API。

## Spec 场景

| Spec ID | 场景 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| `ETC-TICKET-E2E-001` | 页面 ready、三 bucket、四阶段和批次列表 | P0 | 进入 `/etc-tickets` 后显示 ETC 票据标题、未提交/暂存/已提交三个互斥且等宽全宽的状态和计数，选中态填满所属分段；页面不存在月份/车牌/关键词搜索框；左侧列表只能显示当前 bucket 的 business batch，不显示 task-only orphan；右侧按准备资料、确认核对、导入发票、提交 OA 展示四阶段，完成阶段不重复展示解释文字。 |
| `ETC-TICKET-E2E-002` | 发票明细和批次金额证据 | P0 | 选择未提交业务批次后，页面显示 ETC 发票明细、发票号、批次号、发票数量和补充凭证数量；summary 金额和结构化金额必须支持 Workbench/search 使用。 |
| `ETC-TICKET-E2E-003` | 创建 OA 草稿并进入暂存 | P0 | 用户点击提交 OA 后必须打开创建草稿确认 dialog；确认后只调用一次 `POST /api/etc/business-batches/{id}/oa-draft`，成功后批次进入暂存并显示 OA 提交确认 dialog 和打开草稿入口；即使未提交列表 selection 被清空，确认操作仍必须携带该 batch 的最新 version。 |
| `ETC-TICKET-E2E-004` | 人工确认已提交并进入 submitted bucket | P0 | 用户人工点击已提交后只调用一次 `manual-oa-status`；页面切换到已提交 bucket，隐藏提交 OA 入口，显示人工确认已提交状态和原批次证据；不得出现隐藏浏览器错误。 |
| `ETC-TICKET-E2E-005` | 删除/reset 和 relation command safety | P0 | 任意阶段 delete/reset 必须走 business batch 统一删除链路；已提交 summary relation 取消必须通过 Workbench relation command boundary，失败时不得本地半删或恢复旧 OA+银行二栏关系。 |
| `ETC-TICKET-E2E-006` | source file/object storage 和大 ZIP 预览 | P0 | source file 上传必须先落对象存储再追加 metadata；对象存储失败返回结构化错误且不留下半写；大 ZIP preview 不应被普通 API timeout 截断。 |
| `ETC-TICKET-E2E-007` | task-only、新建批次和 durable import recovery | P0 | 新建批次可省略 `taskId`，后端创建 linked task + active business batch；创建失败 tombstone 新 task；durable import restart 后创建 OA 草稿前必须补齐 linked task 状态。 |
| `ETC-TICKET-E2E-008` | Workbench summary fan-out | P0 | 人工已提交业务批次必须在 Workbench open 区形成折叠 `etc_invoice_summary`；已存在 active relation 时 open 区过滤陈旧 summary；delete/reset 后 summary 消失且散票恢复。 |
| `ETC-TICKET-E2E-009` | 权限、旧入口和 regression | P0 | read-only 用户不得触发 OA 草稿、人工确认、删除/reset、source file/upload/import mutation；旧 `/api/etc/batches*` 后端兼容入口、测试 mock 假后端、invoice-id 级 `/api/etc/invoices/revoke-submitted` 和 ETC `oa-status/refresh` 不得回归；已移除 ETC OA 自动检测入口和字段不得回归。 |
| `ETC-TICKET-E2E-010` | 真实基础设施 worker drain | P1 | 真实 PostgreSQL/RabbitMQ/Redis/systemd/OA/对象存储/Nginx 环境下，导入、source file、OA 草稿、人工确认、delete/reset、Workbench summary、税金/成本最终页面展示；该项必须在 staging/runtime smoke 验证。 |
| `ETC-TICKET-E2E-011` | OA 草稿后发票 PDF 合并下载 | P0 | 只有已有 OA 草稿的 actor-scope 业务批次显示下载入口；read-export 用户可下载。服务端以 `business_batch.invoice_ids` 为成员，稳定排序并输出 N 张发票=N 页，任一 PDF 缺失、损坏、hash 不一致或非单页时整体失败；浏览器使用服务端 UTF-8 文件名且无隐藏错误。 |

## 不属于本地 deterministic E2E 的风险

- 真实大 ZIP、票根网 PDF/XML/TXT 混合包、Nginx 上传超时、对象存储权限和 source file 大文件 I/O。
- 真实 OA 草稿页面、附件上传、OA iframe/session/cookie 和人工确认后的真实 OA 系统状态。
- 真实 PostgreSQL + MinIO 中历史批次所有 PDF 的对象 key、hash、字节和页数完整性；发布后需用授权真实批次做只读下载 smoke。
- 生产历史 ETC 迁移、orphan task 清理、旧 business batch pickle 和历史半迁移 relation。
- 真实 PostgreSQL/RabbitMQ/Redis/systemd import/workbench worker drain、tax/cost 页面展示和长队列重试。
- 真实 Workbench、税金抵扣、成本统计、search 全量重建后的最终页面展示。
