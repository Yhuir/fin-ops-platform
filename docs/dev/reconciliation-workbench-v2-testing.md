# 关联工作台 V2 测试与验收

## 1. 当前自动化覆盖

Prompt 15 之后，Workbench V2 的自动化覆盖分成两层：

- 后端：`unittest`
- 前端：`Vitest + Testing Library`

## 2. 已验证场景

### 2.1 后端契约回归

后端继续覆盖：

- `GET /api/workbench`
- `GET /api/workbench/rows/{row_id}`
- `POST /api/workbench/actions/*`
- `GET /api/tax-offset`
- `POST /api/tax-offset/calculate`

目的：

- 保证 Prompt 14 的 JSON 契约不回退
- 保证前端联调不建立在不稳定接口上

### 2.2 前端集成测试

新增覆盖：

- 页面首次加载时请求真实 `/api/workbench`
- 月份切换会重新请求工作台和税金数据
- 点击行只选中，不自动开详情
- 点击 `详情` 才请求行详情并打开抽屉
- `确认关联` 会请求真实动作接口，并带上同 `caseId` 的相关行
- 税金页勾选变化会请求真实 `calculate` 接口并刷新汇总
- 工作台错态展示
- 税金页空态展示

## 3. 当前验证命令

### 3.1 后端全量测试

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
```

### 3.2 前端测试

```bash
cd web
npm run test -- --run
```

### 3.3 前端构建

```bash
cd web
npm run build
```

## 4. 手工验收建议

启动后端：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --host 127.0.0.1 --port 8001
```

启动前端：

```bash
cd web
npm run dev -- --host 127.0.0.1 --port 4174
```

打开：

- `http://127.0.0.1:4174/`
- `http://127.0.0.1:4174/tax-offset`

手工验收重点：

- splitter 可以完整拖拽到收起某栏
- 点击行只选中，不自动弹详情
- `详情` 按钮才能打开抽屉
- 银行栏 `详情 + 更多` 正常渲染
- 月份切换后工作台和税金页都切到真实后端数据
- 税金页结果会随勾选项变化
- 空月份和异常请求都有状态提示

## 5. 当前剩余测试空白

- 还没有浏览器级 E2E
- `关联情况` 仍是前端读状态提示，没有独立后端接口
- Vite 代理默认指向 `8001`，多环境启动仍依赖本地约定或环境变量
