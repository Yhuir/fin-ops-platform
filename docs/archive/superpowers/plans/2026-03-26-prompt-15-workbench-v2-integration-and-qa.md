# Prompt 15 实施记录

日期：2026-03-26

## 已完成

- 新增前端类型与 API adapter
- 工作台页接入真实 `/api/workbench`
- 详情抽屉接入真实 `/api/workbench/rows/{row_id}`
- 行内动作接入真实 `/api/workbench/actions/*`
- 税金页接入真实 `/api/tax-offset` 和 `/api/tax-offset/calculate`
- 补齐 loading / empty / error 状态
- Vite `/api` 代理配置
- 更新 README / Web README / 开发文档

## 验证命令

```bash
cd web
npm run test -- --run
npm run build

PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
```

## 手工验收建议

1. 启动后端到 `8001`
2. 启动 Vite 到 `4174`
3. 在工作台验证：
   - 月份切换
   - splitter 收起 / 恢复
   - 行选中
   - 详情抽屉
   - 确认关联 / 取消关联 / 异常处理
4. 在税金页验证：
   - 月份切换
   - 勾选重算
   - 返回关联台后月份保持
