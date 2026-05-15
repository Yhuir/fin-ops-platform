# fin-ops-platform Agent 导航

这份文件是本仓库的入口地图。它告诉后续 Agent 先读什么、去哪里找事实、哪些内容只作为历史归档。

## 读文档顺序

1. `README.md`：项目定位、运行入口和文档地图。
2. `ARCHITECTURE.md`：系统边界、模块关系、数据流和演进方向。
3. `docs/index.md`：长期文档索引。
4. `docs/product-specs/index.md`：按业务专题阅读需求。
5. `docs/dev/index.md`：按开发任务查接口、测试和本地运行说明。
6. `docs/operations/index.md`：部署、数据重置、备份、监控和故障处理。

## 文档事实源

- 产品和业务口径以 `docs/product-specs/` 为准。
- 系统边界和长期技术决策以 `ARCHITECTURE.md` 和 `docs/architecture/` 为准。
- 运行、测试、接口契约以 `docs/dev/`、`backend/README.md`、`web/README.md` 为准。
- 部署和生产操作以 `docs/operations/` 与 `deploy/oa/README.md` 为准。
- 历史 prompt、旧计划和旧设计只在 `docs/archive/` 追溯，不作为当前需求或架构依据。

## 写文档约定

- 文档默认使用中文。
- 新功能先补 `docs/product-specs/` 或对应开发文档，再改代码。
- 不把新的 Codex prompt 写进主文档树；如需保留，放入 `docs/archive/prompts/`。
- 不在根目录散放临时 Excel、PDF、ZIP、截图或导出物。
- 大文件样例放本地 `fixtures/`，不要让自动化测试依赖真实业务文件。

## 工作约束

- 优先读取现有代码和现有文档，不猜测字段、接口或数据库结构。
- 变更范围保持最小；如果整理范围扩大到重构代码或改变业务口径，先说明并等待确认。
- 生产级需求必须同时考虑权限、审计、回滚、数据一致性和验证方式。
