# 现金账边界与 I/O

## 责任与依赖方向

`Application` 认证/页面授权 → `CashApiRoutes` 解析和 HTTP → cash service 命令/查询 → cash repository SQL → 同库 `cash.*`。

`CashRuntime` 惰性组装专用有界 PostgreSQL 连接，缺少 `FIN_OPS_CASH_POSTGRES_DATABASE_URL` 只使现金 API 返回 503，不使普通 App 启动失败。现金连接必须指向普通 App 同一数据库、使用不同受限登录角色；不继承普通角色、不拥有 cash DDL、不读普通表。池最大 2、等待队列 8、获取超时 2 秒、SQL 超时 5 秒。实际部署须核对全机连接预算。

请求级 `CashOaProjectService` 接收可信 session token 对应的字典读取函数、现金阶段设置读取函数及共享有界 Mongo client。只 GET `XMJD` 字典，Mongo 只投影 form 17 的项目 ID/名称/编号/阶段；不写 OA，不查财务表单，不把 token 留在共享服务中。OA 未配置仅影响依赖它的项目操作；本地历史事项结算不调用 OA。

## 输入

- `/api/cash/*`：必须先认证并拥有页面 `cash`；005 管理员可用，普通账号只有可用/不可用。只有 005 能在既有平台设置修改页面 ACL。
- 金额用两位十进制字符串，日期 ISO、月份 YYYY-MM、ID UUID；未知/重复字段、重复 query key、非法类型和状态明确失败。完整字段与版本见[技术设计](../../dev/cash-module-technical-design.md)。
- 手工创建与任务确认共用同一现金命令事务；核对/未办不造现金。新建真实项目、自由改项目取 OA 当前资格；既有事项结算沿用本地项目。

## 输出和禁止出口

- 现金 DTO 只返回现金页；现金事实包括 flows/items/settlements、任务及配置，共 10 表。报表直接读同一事实，不复制报表流水。
- 写入以一个事务完成，删除正文及关联贡献同步生效；保留其他真实收付。已删 ID 表只含类型与 UUID，不含业务正文。
- cash GET 用短一致只读快照、SQL 聚合/分页；GET 不生成任务实例、不入 queue、不读普通财务。
- cash 全部响应 `Cache-Control: no-store`；全局 requested/completed 审计、App Health 页面事实检查、按接口页面统计都排除现金。HTTP 技术日志只保留通用 `/api/cash`、状态和耗时，不保留 ID/query/业务异常正文。
- Gunicorn 通过 `app/cash_access_logger.py` 同样脱敏现金请求路径，普通日志保持原行为。Nginx/外部日志不属于 Python logger 的控制范围，部署须验证代理层配置；未完成时不得宣称完整生产隐私链已验收。
- 不向 `app.*`、`audit.*`、`job.*` 写入现金操作。平台 ACL 的既有安全审计保留；它不包含现金流水内容。
- 普通 reset、导出、银行余额、成本、往来、发票、worker、read model 不读写 cash。共享登录/数据库原语不是共享财务事实。

## 文件与旧链路

现金代码入口见[README](README.md)，共享改动限 `server.py/http_adapter.py/route_access_policy.py/access_control_service.py` 的组装、精确策略与日志；不更改普通现金收入/cash-special 的业务。它们不是本模块旧版，禁止误删。现金源不用旧 OA active/completed adapter，不恢复已退役 read model 或兼容池。

## 验证与发布

见[测试矩阵](tests.md)、[执行证据](../../dev/cash-module-implementation-plan.md)和[部署说明](../../operations/cash-module-deployment.md)。后端部署不等于页面交付。代码回退保留 cash 数据与权限；禁止 DROP 主数据库或现金业务表。生产只读验证不能代替测试库的写入/并发/回滚验证。
