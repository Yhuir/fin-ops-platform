# 开发文档索引

## 本地开发

- `local-development.md`：本地依赖、启动和检查。
- `backend.md`：后端结构、服务边界和常用入口。
- `runtime-infrastructure.md`：PostgreSQL durable queue、独立 worker、Redis 边界和对象存储配置骨架。
- `runtime-bootstrap.md`：production lightweight bootstrap、repository injection 和 legacy snapshot allowlist。
- `frontend.md`：前端结构、页面和测试入口。
- `testing.md`：测试和验证命令。

## 接口和契约

- `api-contracts.md`：核心 API 分组和契约维护原则。
- `pending-invoices-api.md`：待找发票列表、筛选、关系、候选发票、规则和导出 API。
- `etc-business-batches-api.md`：ETC 业务批次、OA 自动检测、人工兜底和撤销草稿 API。
- `reconciliation-workbench-v2-data-contracts.md`：关联工作台 V2 DTO。

## 历史参考

整理前的阶段性开发说明已归档到 `../archive/legacy-dev/`。如需恢复其中仍有效的内容，先提炼到当前目录或 `../product-specs/`。
