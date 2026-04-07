# Web

正式前端工程已在 `web/` 下落地，当前使用：

- `Vite + React + TypeScript`
- `React Router`
- `Vitest + Testing Library`

当前已提供：

- `OA & 银行流水 & 进销项发票关联台`
- `导入中心`
- `销项票税金 - 进项票税金`
- `成本统计`
- 共享月份上下文
- 工作台上下两区的独立三栏拖拽与收起恢复
- 行选中、高亮联动与居中详情弹窗
- 配置驱动的 OA / 银行流水 / 发票列定义
- 银行 `详情 + 更多` 和未配对 OA / 发票 `确认关联 / 标记异常` 行内动作
- 税金页按月份驱动的销项 / 进项税金勾选与实时试算
- 真实 `/api/*` 数据适配层
- 真实 `/imports/files/*` 文件导入适配层
- `loading / empty / error` 页面状态

保留的原型参考：

- [prototypes/reconciliation-workbench-v2.html](/Users/yu/Desktop/fin-ops-platform/web/prototypes/reconciliation-workbench-v2.html)

本地运行：

```bash
python -m pip install -r backend/requirements.txt
./scripts/start-backend.sh

cd web
npm install
npm run dev
```

说明：

- Vite 已配置 `/api` 与 `/imports` 代理
- 默认代理目标是 `http://127.0.0.1:8001`
- 如需改端口，可通过 `VITE_API_PROXY_TARGET` 覆盖

测试：

```bash
cd web
npm run test -- --run
```

构建：

```bash
cd web
npm run build
```

OA 集成部署补充：

- 正式子路径：`/fin-ops/`
- 嵌入态地址：`/fin-ops/?embedded=oa`
- 页面启动会先请求 `/api/session/me`
- 只有通过 OA 会话和 `finops:app:view` 权限校验后，业务页面才会继续渲染
- 详细部署说明见：
  - `/Users/yu/Desktop/fin-ops-platform/deploy/oa/README.md`

当前工作台拖拽口径：

- `已配对` 与 `未配对` 各自独立拖拽
- 可拖到 `0` 宽收起任意一栏
- 每个 zone 头部按钮只恢复当前 zone 的栏位

当前工作台交互口径：

- 点击行只更新选中状态
- 同 `caseId` 的其他记录会浅蓝联动高亮
- `详情` 只能通过行内按钮打开
- 抽屉会按行请求真实详情，再展示 OA / 银行流水 / 发票三类详情字段
- 银行流水动作先以内联菜单呈现：`关联情况 / 取消关联 / 异常处理`
- 未配对 OA / 发票在行内直接提供 `确认关联 / 标记异常`
- `确认关联 / 标记异常 / 取消关联 / 异常处理` 已接真实后端动作接口
- `关联情况` 当前仍是前端读状态提示，不额外请求后端

当前税金页交互口径：

- 默认全选当前月份所有销项票和进项票
- 勾选变化会调用真实税金计算接口并实时重算：
  - 销项税额
  - 进项税额
  - 本月抵扣额
  - 本月应纳税额 / 留抵税额
- 切换月份会刷新税金清单并重置为新月份默认勾选
- 销项票开票情况只读，进项票认证计划可编辑，右侧抽屉展示已认证结果
- `已认证发票导入` 在税金抵扣页内弹窗完成预览、确认导入和页面刷新
- 当前输出 / 输入行会按后端返回映射为统一前端视图模型

当前成本统计页交互口径：

- 顶部导航已新增 `成本统计`，位于 `税金抵扣` 右侧
- `按时间` 和 `按费用类型` 在页面内各自维护月份或区间选择
- `按项目` 默认统计全部期间，不受月份限制
- 默认显示 `按时间`，字段为：
  - 时间
  - 项目名
  - 费用类型
  - 金额
  - 费用内容
- `按项目` 改成从左到右三列联动：
  - 项目名
  - 费用类型
  - 对应流水
- `按费用类型` 支持左侧选择费用类型、右侧查看对应流水
- 三种视图点具体流水后统一打开详情弹窗
- 已提供 `loading / empty / error` 状态
- 页面头部统一使用一个 `导出中心` 按钮
- `导出中心` 弹窗支持：
  - `按时间`
  - `按项目`
  - `按费用类型`
- `按时间` 和 `按费用类型` 支持：
  - 自定义月份
  - 自定义时间区间（精确到日）
- `按项目` 支持：
  - 选择单个项目
  - 多选费用类型或全选
  - 默认全部期间
- 弹窗底部统一提供：
  - `仅预览`
  - `导出`
- 预览区会展示：
  - 文件名
  - 统计范围
  - sheet 数量
  - 命中条数
  - 金额合计
  - 样例前几行
- 导出成功后页面会显示结果反馈，并按当前配置下载对应 `xlsx`
- 导出文件名会带 `年月或区间 / 统计口径 / 项目名称（如适用）`

当前导入中心交互口径：

- 支持一次上传多份 `.xlsx / .xls`
- 前端会把原文件直接发给后端 `/imports/files/preview`
- 后端自动识别 `发票 / 工商 / 光大 / 建行 / 民生 / 平安` 模板
- 页面会先加载模板库，并支持手动改判模板和发票进销项方向
- 页面按文件展示识别结果、逐行判定、Mongo 留存状态和勾选状态
- 仅勾选文件会进入 `/imports/files/confirm`
- 文件级支持 `/imports/files/retry` 重新识别
- 已确认文件支持批次下载与导入撤销
- 确认导入后页面会展示自动匹配闭环结果，回到工作台即可看到实时刷新数据

后端联调状态：

- Prompt 15 已切到真实 JSON 接口：
  - `GET /api/workbench`
  - `GET /api/workbench/rows/{row_id}`
  - `POST /api/workbench/actions/*`
  - `GET /api/tax-offset`
  - `POST /api/tax-offset/calculate`
- 导入正式化 A 已切到真实文件接口：
  - `POST /imports/files/preview`
  - `POST /imports/files/confirm`
  - `GET /imports/files/sessions/{session_id}`
  - `GET /imports/templates`
  - `POST /imports/files/retry`
  - `GET /imports/batches/{batch_id}/download`
  - `POST /imports/batches/{batch_id}/revert`
- `ReconciliationWorkbenchPage` 与 `TaxOffsetPage` 均已接入这些接口
- `ImportCenterPage` 已接入真实文件导入接口和导入批次配套动作
- 工作台左侧 OA 栏现已支持通过后端实时读取 OA MongoDB
- 自动化测试覆盖了：
  - 月份切换驱动真实请求
  - 详情按需加载
  - 行内确认关联动作请求
  - 税金页真实勾选重算
  - 导入中心批量上传预览、模板改判重试、确认导入、批次撤销
  - 空态 / 错态展示
