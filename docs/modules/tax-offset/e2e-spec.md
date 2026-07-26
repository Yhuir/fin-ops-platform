# 税金抵扣 Browser E2E 规格

| Spec ID | 场景 | 验收 |
| --- | --- | --- |
| `TAX-E2E-001` | canonical 首屏 | GET 200 展示 rows、summary、statistics、认证 drawer；响应无 read-model 状态/版本/refresh metadata |
| `TAX-E2E-002` | 试算 | 修改可选择进项后只调用 calculate，金额与后端规则一致 |
| `TAX-E2E-003` | 计划保存 | 请求携带 canonical token；成功后 normal GET；409 冲突错误可见、无伪成功、不会自动刷新覆盖错误 |
| `TAX-E2E-004` | 认证导入 | preview -> confirm/job -> committed canonical facts -> normal GET；页面请求热路径不解析文件 |
| `TAX-E2E-005` | loading/empty/error | loading、真实空集和失败均用户可见；空集不轮询、不显示 refreshing |
| `TAX-E2E-006` | relation 隔离 | Workbench relation 写前后税金 item 集合与 summary 不变 |
| `TAX-E2E-007` | 权限 | read-export 可读不可写；forbidden/expired 零 protected API；admin 可保存/导入 |
| `TAX-E2E-008` | 大数据交互 | 现有单月表格搜索、日期排序、对方筛选、横向滚动和窄屏操作保持 |
