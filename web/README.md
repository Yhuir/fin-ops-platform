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

## 银行流水拆分

`src/features/bankSplits/` 是银行拆分编辑与读取的前端边界。所有银行详情通过 `BankTransactionDetailContent` 注入现有字段表格；`EntityDetailContent` 只提供纯展示插槽，不读写银行 API。

- 单笔详情：`GET /api/bank-transactions/{id}/splits`，父流水或用途子项身份均由后端解析为完整原流水。
- 多笔详情：`POST /api/bank-transactions/splits/query` 一次读取抽屉中的银行身份，响应与请求顺序对应；不逐个子项请求。
- 保存：`PUT /api/bank-transactions/{id}/splits` 提交版本与完整子项，金额为十进制字符串。前端用整数分校验，后端仍为最终校验与事务 owner。取消拆分明确提交整笔标签。
- `BankSplitEditor` 不自动选择标签、往来归属或填差额；冲突保留草稿，显式重读。全部标签选项来自后端；共享 `TwoColumnTagPicker` 同时用于原成本表单。当前标签 `turnover_role=external_turnover` 时，从 `turnover_third_label_options` 人工选择实例第三级归属。保存完整 `category_label_path`；同 code 编辑保留原路径，换 code 清除旧归属。撤销拆分同样提交整笔实例路径。
- 银行列表保留父流水记录；关联台在同一关系组内按父流水合并显示；若子项分属多个对齐段，银行父容器跨段展示，OA/发票原有分段保持。不同关系组不合并。子项区域是支持 Enter/Space 的 `aria-pressed` 按钮，无可见复选框；选择继续传原子项身份及金额，不把父原额写入选中金额。完整主/子/实例标签显示在各子项内，父金额用默认色，子金额用辅助色，金额均两位小数。
- 保存后的列表回读由所在页面显式负责；当前拆分编辑器采用 PUT 响应更新，列表刷新不重挂载抽屉，不丢弃同抽屉其他银行草稿。关闭重开重新读取详情。原银行余额、流水笔数及非银行详情不在编辑器中计算。

验证入口：`BankSplitEditor.test.tsx`、`BankSplitsApi.test.ts`、`BankSplitRelationCell.test.tsx`、各消费页回归，以及 `e2e/bank-transaction-splits.spec.ts`。浏览器测试使用可持久化的模拟 API，只证明交互与提交合同；真实数据库闭环由后端集成测试证明。
