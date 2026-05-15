# Prompt 15：前后端联调、验收与文档收口

目标：把 Workbench V2 从前端 mock 状态切到真实接口，并完成本轮验收。

前提：

- `12-workbench-v2-bank-and-invoice-actions.md`
- `13-tax-offset-workbench.md`
- `14-workbench-v2-backend-contracts.md`

要求：

- 前端 API 层改成调用真实后端
- 月份切换驱动真实请求
- 详情抽屉按行加载真实详情
- 税金抵扣页改成调用后端数据与计算接口
- 增加 loading / empty / error 状态
- 更新 README 和开发文档中的实现状态

重点验收：

- splitter 可以完整拖拽到收起某栏
- 点击行只选中，不弹详情
- `详情` 按钮才能打开抽屉
- 银行栏动作正常渲染
- 税金页结果与勾选项一致

验证：

- 前端测试通过
- 后端测试通过
- 手工验收通过
- 文档与实现一致
