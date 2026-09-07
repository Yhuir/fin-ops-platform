# 现金后端部署：同库、同账号、独立表

更新：2026-09-07。用户明确现金不使用单独数据库登录账号。本文件替代先前专用cash账号和API专用env的安装方案；历史执行证据保留在[实施计划§10](../dev/cash-module-implementation-plan.md)，不把旧计划或旧验证当作当前配置。

2026-09-08统一UI/多选读取发布：不增加数据库迁移或生产写操作，前后端使用同一已提交现金分支候选，由既有deploy-oa.sh正式检查/激活。部署前后同条件只读测量、活动release、全部验证与例外统一记录[实施§14](../dev/cash-module-implementation-plan.md#14-统一现金ui实际执行与验证2026-09-08)。下文具体旧版本性能是历史，不代表此次发布结果。生产浏览器显式阻断非GET/HEAD/OPTIONS，且关闭敏感截图、trace和录像；不创建受限角色或试验现金。保留可回滚release，本次不清理其他发布资产。

## 数据和连接边界

- 只有现有生产PostgreSQL数据库`fin_ops`，普通业务在app等既有schema，现金在`cash.*`十张表。没有第二个现金数据库。
- 现金直接复用`PostgresSettings.from_env()`及现有common/secrets配置。生产只读核实API账号为`fin_ops_app_runtime`、PostgreSQL 16.12；不从服务器root密码推导数据库密码。
- 不创建cash登录账号、不使用`FIN_OPS_CASH_POSTGRES_DATABASE_URL`、不安装`/etc/fin-ops/fin-ops.cash.env`。旧账号provision工具、身份检查模块、env示例和systemd/helper加载项已移除；不保留双配置或自动兼容分支。
- cash runtime保留独立小池：最多2连接/8等待/2秒获取/5秒SQL超时，既有更严限制不放宽。它只约束资源占用，与普通池连接相同数据库和账号。
- 同账号在数据库层能够访问普通表和现金表，不能再宣称数据库账号级隔离。cash API仍先认证及页面授权，cash repository只读写cash.*，普通页面/导出/reset/worker不得访问cash；全局操作历史和页面统计不记录cash。模块I/O及普通测试承担应用隔离责任。

## 发布顺序

**已于2026-09-07 17:48 CST完成正式发布，release=`cash-8bdfc07ae-20260907-ui`，代码=`8bdfc07ae`。** 按App前端与本地真实API联调→既有发布条件→提交推送cash分支→正式发布及生产只读验证执行，既有发布证据PASS。此前`7a0d272e`候选依赖已取消的专用账号设计，不可激活。实际本地结果见实施计划§10.13，发布、隐私、性能和未测风险见§10.14；下面为保持的发布规则。

该服务器当前API单元是`fin-ops.service`，其WorkingDirectory直接指向本release的src，四worker为`fin-ops-worker@<name>.service`；没有`/opt/fin-ops/current`软链接。运维以实际systemd属性和正式发布证据确认活动版本，勿用不存在的单元或泛用示例路径替代核查。

1. 发布届时已提交并推送的`codex/cash-ledger`，不合并main；现金前端入口只能在新版UI确认后实现。用现有`./scripts/deploy-oa.sh`完成新候选检查。
2. 保持历史0166不变；追加`0167_cash_shared_runtime_grants.sql`为**已存在的**`fin_ops_app_runtime`授予cash schema USAGE以及明确10表SELECT/INSERT/UPDATE/DELETE。迁移不创建角色、不授予DDL、TRUNCATE、所有权或普通业务新增权限。角色不存在时明确报错，不另造账号。
3. 依照既有发布规则，在实际PostgreSQL 16隔离测试数据库上验证上一release代码与0166、0167每个候选schema head的固定写操作矩阵；兼容证据必须是真实执行结果，不可填造或跳过。
4. 若服务器曾安装带cash env加载项的helper，使用现有hash-pinned bootstrap更新为最新已验证候选；只替换helper不顺带迁移或重启。本次已安装`8bdfc07ae`版本，旧cash env加载项已移除；语法/既有contract检查通过，root:root/0755。现金env不存在，未创建或删除密钥文件。
5. 完成下述代理日志隐私配置，运行`nginx -t`；在正式发布窗口应用。普通请求诊断保持不变。
6. 用`./scripts/with-production-admin-token.sh ./scripts/deploy-oa.sh ...`正常激活；按现有流程迁移、切换和验证，不新增门禁，不删除既有安全措施。API仍只加载现有common/secrets。
7. 验证现金只读API、真实OA项目/状态读取、旧页面API及worker、全局历史排除和混合负载。无真实现金数据时，空表耗时不能代表满量性能；生产不插入试验现金，写入/任务/删除/回滚在明确隔离测试库验证。

## Nginx与日志

2026-09-07只读核实线上Nginx使用`/www/server/nginx/conf/nginx.conf`，域名server块也在此文件中。不是此前猜测的`/www/server/panel/vhost/nginx/www.yn-sourcing.com.conf`。

三个现有API入口都需处理：

| 外部前缀 | 现金路径 |
| --- | --- |
| `/api/` | `/api/cash`及子路径 |
| `/fin-ops/api/` | `/fin-ops/api/cash`及子路径 |
| `/fin-ops-api/` | `/fin-ops-api/api/cash`及子路径 |

发布前检查发现三个入口没有cash日志例外，本轮已在真实配置中安装精确排除。应用/Gunicorn将现金技术路径脱敏为通用`/api/cash`，代理对上述精确cash路径段关闭access记录，不影响cash-back等近似前缀及普通页面日志。不采集真实现金正文作为验证样本，不打印token或金融内容。

仓库示例及活动配置使用http级`map $uri $fin_ops_access_loggable`和站点条件access_log实现三个精确前缀排除；`$uri`归一化后再匹配，兼容现有rewrite。正式安装只局部补丁，候选/活动配置`nginx -t`均通过后reload，保留OA代理和TLS。三个现金别名实测认证200/匿名401且no-store；带非敏感标记的3次现金请求access记录0条，cash-back邻近请求403且记录1条，验证未误关普通日志。

## 验证、清理与回退

- 本机admin token统一经`scripts/with-production-admin-token.sh`加载，HTTPS必须验证证书；不打印token、完整身份和业务payload。
- 同账号集成测试在显式`fin_ops_cash_test_*`本地测试库运行：真实现金API创建/读取/删除、余额恢复、同ID普通数据不变、十表授权以及页面/审计隔离。测试库仅合成数据；结束后关闭连接并精确清理自身库，禁止删除主数据库。
- 缺PG配置、连接失败、缺表或权限不足时cash返回明确503；不使用替代数据库、内存流水或假成功。服务active/旧版health为ready不等于现金版本上线。
- 普通App共享基础设施，不能承诺零资源影响；必须分别报告旧版/新版、并发数、样本数、p50/p95/p99和错误。此前旧工作台4并发p95超标不能归因于现金，也不能通过降低阈值隐藏。
- 不创建本任务数据库备份；既有发布若要求任务专属恢复工件，按[数据安全流程](data-safety.md)验证后精确清理。保留组织PITR/永久备份、生产cash表及业务数据，禁止删除主库。
- 代码回退保留cash事实，不能回退到把现金写入普通池/全局历史的代码。0167不收回旧权限、不改普通表数据；遵守实际发布兼容证据和历史forward-only约束。
- 本轮App已上线并完成有界生产只读检查，现金事实和配置仍为空；首次真实账户/期初/任务/OA允许阶段由用户使用时设置。生产浏览器已覆盖现金全部视图和旧16页面，未做生产现金写入或受限角色验证；真实写入浏览器耗时未测。工作台4并发p95发布后1124.80ms，仍未达到1000ms目标，不以混测较快结果覆盖该例外。
- 任务专属Nginx配置副本和候选暂存目录已验证后精确清理；保留活动配置、旧release、正式兼容及发布证据。本次没有数据库备份，也没有删除主库或既有备份。纯文档收尾提交不重复部署应用。

接口及隔离事实见[现金边界](../modules/cash/boundary-io.md)和[技术设计](../dev/cash-module-technical-design.md)。当前实际进度只以[实施记录](../dev/cash-module-implementation-plan.md)为准。
