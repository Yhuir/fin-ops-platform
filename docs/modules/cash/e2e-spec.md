# 现金端到端范围

后端链路按[实施计划 B09/B10](../../dev/cash-module-implementation-plan.md)及[技术设计 TC01–TC28](../../dev/cash-module-technical-design.md)执行。

浏览器当前已覆盖四子页面与既有业务，历史证据见实施计划§12。统一UI用例按[UI§3.6](../../product-specs/cash-module-ui-spec.md#36-全现金模块统一ui结构)和[实施§13.5–13.6](../../dev/cash-module-implementation-plan.md#135-测试责任与命令)落实，实际结果见实施§14；F01–F05只是首次建设历史。

本轮重点：所有视图/抽屉菜单打开、搜索/翻页、勾选/取消/应用、加载失败/空值/超限、列排序、固定布局与焦点、退出/撤权。至少一条浏览器→真实本地现金API→disposable PG的录入/筛选/删除链；允许本地身份与非现金Shell使用fixture，现金I/O不能拦截伪造。生产只读单独记录，不创建受限角色。
