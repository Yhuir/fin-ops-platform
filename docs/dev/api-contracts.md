# API 契约

## 契约原则

- API 返回字段应稳定，前端不能猜测不存在的字段。
- 写操作返回 affected rows/months，便于前端局部刷新。
- 高风险动作应有 preview 或 confirm 两段式接口。
- 后端错误应返回可展示的业务消息，不返回空 body 让前端猜测。
- HTML 响应视为部署或代理错误。

## 主要 API 分组

- `/api/session/*`：OA 会话和当前用户。
- `/api/workbench*`：关联工作台查询、详情、动作、异常、设置。
- `/imports/*`：导入预览、确认、模板、批次和文件会话。
- `/api/no-oa-bank-batches/*`：免 OA 批次。
- `/api/etc/business-batches*`：ETC 用户可见业务批次、补充导入、OA 草稿、OA 自动检测、人工兜底和撤销草稿。详细合同见 `etc-business-batches-api.md`。
- `/api/tax-offset*`：税金抵扣和已认证导入。
- `/api/cost-statistics*`：成本统计、下钻和导出。
- `/api/bank-details*`：银行明细和分类。
- `/api/background-jobs*`：后台任务。
- `/api/app-health*`：健康状态。

## 工作台 DTO

工作台 DTO 的详细结构见 `reconciliation-workbench-v2-data-contracts.md`。

## ETC 业务批次 API

ETC 对账任务、ZIP 导入和 OA 草稿提交统一使用 `/api/etc/business-batches*` 作为新增契约层。它取代前端直接拼接 `EtcImportBatch` 和 `EtcBatch` 的展示口径，旧 `/api/etc/batches*` 只作为过渡兼容入口，不应继续扩展。

详细状态枚举、错误码、权限、幂等和撤销草稿/释放发票规则见 [`etc-business-batches-api.md`](etc-business-batches-api.md)。设计依据见 [`../superpowers/specs/2026-05-19-etc-business-batch-oa-auto-detection-design.md`](../superpowers/specs/2026-05-19-etc-business-batch-oa-auto-detection-design.md)。

## 版本和兼容

当前项目仍保留部分旧接口。新增能力应优先接入 `/api/*` 契约层；旧接口只用于兼容测试或历史页面，不应继续扩展。
