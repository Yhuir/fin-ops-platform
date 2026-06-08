# fin-ops-platform

`fin-ops-platform` 是一个以银企核销为核心的财务运营平台，覆盖导入、关联工作台、核销、台账、OA 接入、税金抵扣、ETC、成本统计、银行明细、免 OA 批次和后台任务治理。

## 当前技术栈

- 后端：Python，业务服务在 `backend/src/fin_ops_platform/`。
- 前端：React + TypeScript + Vite，正式工程在 `web/`。
- 持久化：生产主读写使用 PostgreSQL；OA MongoDB 继续只读接入。app Mongo 旧路径保留为迁移观察期回滚、shadow-read 和审计工具使用。
- 部署：支持 OA 同域 iframe 集成，前端 `/fin-ops/`，后端 `/fin-ops-api/`。

## 快速启动

安装后端依赖：

```bash
python -m pip install -r backend/requirements.txt
```

检查后端：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

启动后端：

```bash
./scripts/start-backend.sh
```

启动前端：

```bash
cd web
npm install
npm run dev
```

## 验证

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
cd web && npm test
cd web && npm run build
```

## 文档入口

- Agent 导航：`AGENTS.md`
- 架构总览：`ARCHITECTURE.md`
- 产品和界面原则：`DESIGN.md`
- 可靠性基线：`RELIABILITY.md`
- 安全和权限：`SECURITY.md`
- 文档地图：`docs/index.md`
- 当前 app 架构：`docs/app-architecture/README.md`
- 页面和功能模块维护：`docs/modules/README.md`
- 产品规格：`docs/product-specs/index.md`
- 开发文档：`docs/dev/index.md`
- 运维文档：`docs/operations/index.md`
- 部署说明：`deploy/oa/README.md`

## 仓库结构

```text
backend/        Python 后端
web/            React 前端
tests/          后端测试
docs/           长期文档和归档
deploy/         部署资产
fixtures/       本地手工验收样例，不作为自动化测试事实源
scripts/        开发和运行脚本
```

## 归档说明

历史 prompt、旧计划和阶段执行记录不再保留为当前文档入口。仍有价值的结论已提炼到长期文档，原始业务源少量保留在 `docs/references/`。
