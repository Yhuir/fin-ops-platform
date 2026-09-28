# 财务运营平台

面向财务人员的 OA、银行流水与发票核对平台，提供导入、关联、进销项、税金、成本、往来和独立现金业务。前端 React + TypeScript，后端 Python HTTP API，业务事实保存在 PostgreSQL。

## 设计与架构

本仓库只维护一套当前版本说明，按模块拆分以便定位，不保存开发计划、执行日志、退役说明或重复规范。

- [系统架构](ARCHITECTURE.md)：边界、数据流、事务、性能和部署形态。
- [模块与页面](docs/modules/README.md)：每个页面和共享能力的 I/O、业务规则、依赖与实现入口。
- [界面约定](docs/ui.md)：公共组件、状态、金额、表格与交互。
- [开发与验证](docs/development.md)：本地运行、测试、脚本与隔离测试库。
- [部署与运行](docs/operations.md)：发布、监控、凭证、恢复和数据安全。
- [Agent 导航](AGENTS.md)：修改代码和文档的最小协作规则。

## 本地启动

```bash
python3 -m pip install -r backend/requirements.txt
cd web && npm ci
```

准备本地专用运行环境后，在独立终端分别运行 `./scripts/start-backend.sh` 与 `./scripts/start-web.sh`。具体配置见[开发说明](docs/development.md)。生产使用 `./scripts/deploy-oa.sh`。
