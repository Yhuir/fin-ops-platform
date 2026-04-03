# Backend

当前后端采用零外部依赖的 Python 骨架，目标是先把领域模型、模块边界和最小服务跑起来，后续再按需要替换为更正式的 Web 框架。

目录说明：

- `src/fin_ops_platform/app`：HTTP 入口与路由
- `src/fin_ops_platform/domain`：核心领域枚举与模型
- `src/fin_ops_platform/services`：审计、seed 数据等基础服务

本地检查：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

本地启动：

```bash
./scripts/start-backend.sh
```

说明：

- 启动脚本默认以 `FIN_OPS_STORAGE_MODE=mongo_only` 运行
- 生产模式下 app 状态快照与原始导入文件都写入 Mongo
- OA 数据库 `form_data_db` 继续保持只读，app 自身状态写入独立库 `fin_ops_platform_app`
