# Web

正式前端工程位于 `web/`，使用 Vite、React、TypeScript、React Router、Vitest 和 Testing Library。

## 本地运行

```bash
cd web
npm install
npm run dev
```

Vite 默认代理：

- `/api` -> `http://127.0.0.1:8001`
- `/imports` -> `http://127.0.0.1:8001`

如需改端口，设置 `VITE_API_PROXY_TARGET`。

## 测试与构建

```bash
cd web
npm test
npm run build
```

## 页面范围

- 关联工作台。
- 银行流水、发票和 ETC 发票三个导入工作流。
- 银行明细。
- 税金抵扣。
- ETC 相关页面。
- 成本统计。
- 设置页。
- App health 和后台任务状态。

## OA 集成

- 正式子路径：`/fin-ops/`
- 嵌入态地址：`/fin-ops/?embedded=oa`
- 页面启动会先请求 `/api/session/me`
- 只有通过 OA 会话和权限校验后，业务页面才继续渲染

## 相关文档

- `../docs/dev/frontend.md`
- `../docs/product-specs/workbench.md`
- `../docs/product-specs/settings-and-access-control.md`
- `../deploy/oa/README.md`
