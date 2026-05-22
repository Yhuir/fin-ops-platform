# 本地开发

## 后端依赖

```bash
python -m pip install -r backend/requirements.txt
```

后端基础检查：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

后端启动：

```bash
./scripts/start-backend.sh
```

启动脚本会优先读取本地私有环境文件：

```text
.runtime/fin_ops_platform/local-postgres.env
```

该目录已被 `.gitignore` 忽略，适合放 PostgreSQL、MinIO/S3 和 SSH tunnel 凭据。文件存在且包含 `FIN_OPS_POSTGRES_DATABASE_URL` 或 `DATABASE_URL` 时，`./scripts/start-backend.sh` 会默认使用 PostgreSQL runtime：

- `FIN_OPS_APP_STORAGE_BACKEND=postgres`
- `FIN_OPS_APP_READ_BACKEND=postgres`
- `FIN_OPS_POSTGRES_CUTOVER_PHASE=postgres_primary`
- `FIN_OPS_STORAGE_MODE=postgres`

如果配置了 `FIN_OPS_SSH_TUNNEL_HOST`，启动脚本会先建立本地端口转发，再启动 API：

- `FIN_OPS_SSH_TUNNEL_PG_PORT`，默认 `15432`，转发到服务器 PostgreSQL。
- `FIN_OPS_SSH_TUNNEL_S3_PORT`，默认 `19000`，转发到服务器 MinIO/S3 endpoint。
- `FIN_OPS_SSH_TUNNEL_REDIS_PORT`，配置后转发到服务器 Redis；未配置则不创建 Redis tunnel。

已有端口转发时脚本不会重复创建 tunnel。需要使用其他环境文件时：

```bash
FIN_OPS_BACKEND_ENV_FILE=/path/to/local.env ./scripts/start-backend.sh
```

如果非交互 shell 解析到的 `python3` 不是当前开发环境，可以在本地 env 文件中设置 `FIN_OPS_PYTHON_BIN=/path/to/python3`。

需要让本地和服务器都启用 Redis runtime helper 时，服务器 systemd env 和本地私有 env 都应配置 `FIN_OPS_REDIS_URL`。本地通常使用 SSH tunnel，例如 `redis://:password@127.0.0.1:16379/0`。

生产级本地验收应先跑 runtime check：

```bash
./scripts/check-local-runtime.sh --dependencies-only
```

该检查会确认本地到服务器 PostgreSQL、Redis、MinIO/S3 的连接，以及 facts/read model 的基础行数。`./scripts/start-backend.sh` 在检测到 PostgreSQL runtime 时也会自动执行这一步；依赖不可用时直接失败，不启动一个“看起来在跑但实际不能读 PG”的后端。

后端启动后再跑完整 smoke：

```bash
./scripts/check-local-runtime.sh --require-backend
```

完整检查会验证 `/health` 使用 PostgreSQL runtime、Redis 和对象存储可用，并确认 `/api/workbench?month=all` 能从 SQL read model 返回非空数据。

没有 PostgreSQL 连接配置时，脚本仍保留本地 legacy mode 兼容路径；本地和服务器同构验收必须使用 PostgreSQL runtime。

## 前端依赖

```bash
cd web
npm install
../scripts/start-web.sh
```

本仓库本地 Web 默认监听 `http://127.0.0.1:4173`，API 代理到 `http://127.0.0.1:8001`。如果机器上 `5173` 正被其他 Vite 项目占用，不要用 `5173` 判断本项目状态。

正式构建：

```bash
cd web
npm run build
```

## OA 配置

本地真实 OA Mongo 接入可配置：

- `.runtime/fin_ops_platform/oa_mongo_config.json`
- 或环境变量 `FIN_OPS_OA_MONGO_*`

App Mongo 可配置：

- `.runtime/fin_ops_platform/app_mongo_config.json`
- 或环境变量 `FIN_OPS_APP_MONGO_*`

## 常见检查

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
cd web && npm test
cd web && npm run build
```
