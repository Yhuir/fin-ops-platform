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

启动脚本默认使用 `FIN_OPS_STORAGE_MODE=mongo_only`。如果没有配置 app Mongo，先阅读 `backend/README.md` 和本地 `.runtime/fin_ops_platform/` 配置说明。

## 前端依赖

```bash
cd web
npm install
npm run dev
```

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
