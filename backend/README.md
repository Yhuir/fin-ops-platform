# Backend

后端是 Python 服务，负责导入解析、OA 接入、关联工作台、核销、台账、税金、ETC、成本统计、设置、后台任务和 app health。

## 目录

```text
backend/src/fin_ops_platform/
  app/       HTTP 入口、路由、OA 鉴权、响应组装
  domain/    领域模型和枚举
  services/  业务服务、适配层、持久化、读模型和后台任务
```

## 本地检查

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

## 本地启动

```bash
./scripts/start-backend.sh
```

## 测试

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
```

## 持久化

- 启动脚本默认以 `FIN_OPS_STORAGE_MODE=mongo_only` 运行。
- 生产模式下 app 状态快照、明细集合和原始导入文件写入 app Mongo。
- OA 数据库保持只读，app 自身状态写入独立库 `fin_ops_platform_app`。

## 相关文档

- `../ARCHITECTURE.md`
- `../docs/dev/backend.md`
- `../docs/architecture/persistence-and-read-models.md`
- `../docs/operations/deployment.md`
