# 操作历史

入口：`/operations/history`。

提供管理员查询追加型审计事件，按请求聚合业务动作、结果、操作者和固化证据；不修改业务事实。

## 边界与 I/O

输入：管理员 session、日期/人员/页面/keyword/cursor 或 operation_key。输出：列表、完整去重操作者选项及 target/artifacts/records/changes/failure 详情。

## 当前业务约定

- 事实源为 audit.events，列表在数据库内先聚合 request_id 再筛选分页，最多 200 条，稳定时间与 key 游标。
- unsafe 请求先记录 requested，失败则不执行业务写；同请求领域事件继承 request ID。成功/失败结果如实保存。
- 财务关键字段修正要求事务 actor/reason，并同事务追加 financial_fact_corrections 和 audit，历史不可变。
- 来源证据在写入时固化，查询不依赖可变业务表重造历史；展示过滤 secret、raw payload 和内部标识。
- 收据记录生成及打印请求，不声称实际打印完成；现金操作不进入此历史。
- 列表和详情分别取消过时请求，迟到响应不覆盖当前选择。

## 依赖方向

[权限与审计](../permissions-and-audit/README.md)、[正式关联关系](../workbench-relations/README.md)、[现金账](../cash/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口


通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。
