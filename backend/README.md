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

- 生产主读写通过 `FIN_OPS_APP_STORAGE_BACKEND=postgres` 和 `FIN_OPS_APP_READ_BACKEND=postgres` 接入 PostgreSQL。
- PostgreSQL 连接使用 `FIN_OPS_POSTGRES_DATABASE_URL` 或 `DATABASE_URL`，生产环境应从 root-only credential file 注入。
- app Mongo 旧路径仍保留，用于迁移观察期回滚、shadow-read、导出和审计工具。
- OA 数据库保持只读，只能通过 `MongoOAAdapter` 读取，不能作为 app 写库。

## 相关文档

- `../ARCHITECTURE.md`
- `../docs/dev/backend.md`
- `../docs/architecture/persistence-and-read-models.md`
- `../docs/operations/deployment.md`
