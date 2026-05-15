# fin-ops-platform

`fin-ops-platform` 是一个以银企核销为核心的财务运营平台，覆盖导入、关联工作台、核销、台账、OA 接入、税金抵扣、ETC、成本统计、银行明细、免 OA 批次和后台任务治理。

## 当前技术栈

- 后端：Python，业务服务在 `backend/src/fin_ops_platform/`。
- 前端：React + TypeScript + Vite，正式工程在 `web/`。
- 持久化：生产模式使用 app MongoDB detailed collections 和 GridFS；OA MongoDB 只读接入。
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

历史 prompt、旧计划和旧设计已经移入 `docs/archive/`。它们只用于追溯，不作为当前需求、架构或验收标准。
