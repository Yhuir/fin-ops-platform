# fin-ops-platform 协作入口

先读 [README](README.md)、[系统架构](ARCHITECTURE.md)，再从[模块索引](docs/modules/README.md)定位直接模块及上下游。每个模块的 README 是其职责、I/O、业务不变量和测试入口的唯一文档。

- 先核对代码、API/schema 与测试，不把文档描述当作实现证据。当前页面从 PostgreSQL canonical facts 直读。
- 保持模块化单体与明确 owner；route 只做鉴权、参数和 HTTP 映射，业务在 service，SQL 在 repository，异步执行在登记 worker。
- 修改前识别输入/输出、调用方、共享状态、权限和跨页面影响。删除符号时全仓检查静态引用、动态注册、部署配置、测试和文档。
- 复用既有能力，保持最小差异。不加隐藏 fallback、兼容旧链、重复抽象或无实际用途的门禁。不能把正常错误处理、幂等和事务回滚当作冗余删除。
- 新行为先明确合同，再修改有意义的相关测试；纯文档不机械新增业务测试。验证入口见[开发说明](docs/development.md)。不能用跳过、放宽断言或删除有效测试隐藏失败。
- Python 修改运行 `bash scripts/verify.sh lint`；必要时只对相关文件用 Ruff 修复 import 排序。
- 文档默认中文，只维护当前事实，不生成计划、状态日志、执行记录或退役说明。修改边界/业务/操作方式时更新对应最终文档；纯内部实现可说明文档不适用。
- 不默认启动 GSD、建立新文档体系或做无关重构。范围扩大到业务/API/数据库结构变化时先明确说明。
- 生产发布只用 `./scripts/deploy-oa.sh`，具体安全和恢复合同见[运行说明](docs/operations.md)。生产 token 只通过 `scripts/with-production-admin-token.sh <command>` 加载，不打印或提交。
- 主数据库不可删除。测试使用明确可丢弃的独立数据库；任务自产恢复工件验证后按对应工具的精确清理合同删除，不触碰常规备份。
- 完成后报告改动、验证命令、实际结果和剩余风险；涉及行为修改时说明七类测试的适用性：业务、service、API、异步/缓存、前端、跨模块链路、既有回归。
