# 现金账后端部署与首次数据库授权

现金后端使用现有 PostgreSQL 数据库的 `cash` schema，不新建生产数据库。后台接口独立使用受限 cash 登录角色；普通 API、worker、只读账号不得取得 cash 权限。现金角色不拥有表、不执行 DDL、不继承其他角色、不读取普通财务表。

本次用户明确授权从 `codex/cash-ledger` 分支部署后端，不合并 `main`，不新增前端导航或现金权限复选框。正式发布仍使用 [`scripts/deploy-oa.sh`](../../scripts/deploy-oa.sh) 及[现有部署流程](../../deploy/oa/README.md)。本文只补充现金所需的一次性管理员配置，不替换现有发布验证。

## 职责和顺序

1. 发布负责人确定已提交、已推送的 exact 分支 commit 和候选 release；先执行正常候选验证。
2. 通过现有 migrator 流程执行 `0166_cash_ledger.sql`，创建现金 10 表。migration 不创建登录角色、不猜测普通运行角色、不自动扩展原 App 授权。
3. DBA 使用显式管理员连接执行下述一次性配置工具；验证 cash 与所有实际普通运行角色双向隔离。
4. 系统管理员安装 API 专用密钥文件和加载配置，再由正常发布流程激活候选版本。
5. 执行真实登录、现金只读 API、原页面回归、OA 只读联通与性能验证，记录实际结果。没有真实现金业务数据时，生产空表耗时不能代表满量性能；写入、删除、任务及事务链路在独立测试数据库验证。

步骤 2—4 涉及现有发布维护窗口和数据库安全边界，须由发布负责人协调。不得为绕过授权，把候选脚本塞进既有 root helper 的其他功能执行。`finops-deploy` 的现有受限 sudo 不等于数据库管理员或任意 `/etc` 写权限；migrator 具备 DDL 权限也不代表它具有 `CREATEROLE`。

## 一次性角色配置工具

入口：[`scripts/provision_cash_postgres.py`](../../scripts/provision_cash_postgres.py)。只依赖现有 Python/psycopg，不创建数据库、不写业务记录、不安装环境文件、不改 systemd。

### 显式输入

| 环境变量 | 内容与用途 |
| --- | --- |
| `FIN_OPS_CASH_PROVISION_ADMIN_DATABASE_URL` | 此次操作专用 DBA DSN；新建角色要求 `CREATEROLE` 或管理员权限，并且能够授予指定数据库/schema/表权限。不能作为 cash runtime DSN。 |
| `FIN_OPS_CASH_POSTGRES_DATABASE_URL` | 计划安装到 API 的真实 cash 登录 DSN；明确 host、dbname、user、password。使用新建的独立角色，或事先已存在且满足限制的角色。 |
| `FIN_OPS_CASH_ORDINARY_DATABASE_URLS` | 非空 JSON 字符串数组，列出生产实际使用的普通 API、worker、只读连接。不能只检查一个方便取得的账号；相同角色的多个连接仍会分别真实登录验证。 |

所有连接必须显式指向相同 host、hostaddr、port 和 dbname。禁止不同数据库、跨端点“应该是同库”的推断、连接 `service/options` 覆盖和 cash/普通角色复用。工具还会核对真实 `current_user`、`session_user` 和数据库名，不能通过 `SET ROLE` 假装独立登录。

管理员在服务器上准备仅 root 可读的临时凭据文件，例如明确命名为 `/root/fin-ops-cash-provision.env`，权限 `0600`，不提交仓库、不打印、不启用 shell `xtrace`。真实 DSN 应通过受信任的凭据渠道录入，不复制到聊天或命令参数。以下命令中的 release 路径必须换成已核实的候选路径，Python 使用当前生产 venv 的实际路径：

```bash
set +x
set -a
source /root/fin-ops-cash-provision.env
set +a
/opt/fin-ops/venv/bin/python /opt/fin-ops/releases/<exact-release>/src/scripts/provision_cash_postgres.py --apply
```

`--apply` 的单一事务只做：新建指定受限登录角色（若不存在）、授予数据库 `CONNECT`、cash schema `USAGE`、10 表 `SELECT/INSERT/UPDATE/DELETE`。主键为 UUID，不授予 sequence 权限。不授予表所有权、schema/database `CREATE`、`TRUNCATE` 或 grant option；不添加角色成员关系。密码使用 PostgreSQL/libpq 原生 SCRAM 认证处理，不增加业务 hash。

已存在的高权限角色、跨池权限、PUBLIC/默认授权造成的泄漏、cash 可执行的用户 schema `SECURITY DEFINER` 函数以及普通角色可切换至 cash 高权限角色都会明确报错。工具不会自动降权、轮换既有密码、撤销普通权限或修改主数据库内容。DBA 应定位实际授予路径并评估影响后纠正，不做宽泛 `REVOKE`。仓库 `0007_grants.sql` 只授予显式普通 schema，未设置全局默认授权；仍需检测服务器实际有效权限，不能从仓库推断生产从未被人工授权。

提交后工具使用 cash 和每个普通 DSN **真实连接**：cash 能读取 `cash.flows LIMIT 0`，普通连接必须明确得到权限拒绝；不会读取任何现金金额或业务正文。

### 只读复查与失败处理

安装前后可使用同样的受保护输入运行 `--check`。该模式不创建角色、不授予权限，管理员事务为只读；随后执行真实登录与 `LIMIT 0` 权限探测。

输出只含状态、角色/表数量和安全错误码，不含 DSN、密码或金融数据。失败结果必须结合 `database_changes_committed` 判断：

- `false`：配置事务没有提交；例如现金表未迁移、普通角色已有现金授权，新建角色及本次 grants 均回滚。
- `true`：配置已提交，但后续真实登录或权限复查失败；例如 pg_hba 拒绝 cash 登录。保留角色与数据，修正明确的连接/认证配置后重新检查；不得误报“已回滚”，也不得自动删除角色。
- `cash_role_not_provisioned`：`--check` 检测到 cash 角色尚未建立，需要 DBA 执行首次配置。
- `cash_migration_0166_exact_tables_required`：先完成对应迁移，不能凭空建立替代表。
- `ordinary_runtime_has_cash_privileges`、`ordinary_runtime_can_assume_cash_privileged_role`：普通账号隔离不成立，管理员检查有效授权与成员关系。
- `database_connection_or_operation_failed`：工具为避免泄漏连接秘密而输出脱敏错误；管理员在受控环境定位认证、网络或授权问题，不把原始异常复制到公开日志。

## API 专用环境文件

永久密钥文件为 `/etc/fin-ops/fin-ops.cash.env`，必须是 root 所有的普通文件、权限 `0600`，不得用符号链接。该文件只放 `FIN_OPS_CASH_POSTGRES_DATABASE_URL`；不放管理员 DSN、普通 DSN 数组、OA token，也不覆盖普通 PostgreSQL 配置。不要把 cash DSN 放进 API/worker 共用的 `fin-ops.secrets.env`。

系统管理员通过受保护编辑器或现有秘密管理方式安装实际值。本文不提供带真实密码的 shell 行，不允许普通部署账号借 helper 任意写 `/etc`。

API `fin-ops.service` 需要独立加载该文件。发布 helper 的 `write_api_dropin` 在已有 common/secrets 后，为 API 生成以下行：

```ini
[Service]
EnvironmentFile=-/etc/fin-ops/fin-ops.cash.env
```

这不是另建一套 drop-in：现有 `99-deploy-release.conf` 会重置环境文件列表，helper 还会清理非现役 `.conf`，所以不能用额外 `zz-*.conf` 绕过既有治理。更新后的受控 helper 保留原加载顺序，只在 API 段增加该文件；文件存在时检查其安全属性。不把此行加入 worker 配置。系统管理员必须先通过现有受控 bootstrap 更新 root helper，再由正常发布生成配置。

这里的 `-` 只表示尚未开通现金模块时该文件可以缺席，不替换 DSN 或放宽角色权限；普通页面不应因现金尚未配置而无法启动。发布负责人通过 `systemctl show fin-ops.service -p EnvironmentFiles --no-pager` 核对最终加载**文件路径**，不打印 Environment 的秘密值；协调 `daemon-reload` 和后续正常发布激活，不提前重启在用服务。

现金连接缺失或受限身份不正确时，现金 API 返回明确的 503，普通页面仍正常；这是缺少依赖的可见错误，不是退回普通数据库身份。首次部署在上述 API env/role 配置确认后才能宣称现金后端生产可用。

## 验证、清理与回退

- 角色测试：`tests/test_cash_postgres_permissions.py` 使用显式 `FIN_OPS_CASH_PROVISION_TEST_ADMIN_URL`，创建随机、独立的测试数据库与角色，执行真实 DML、双向拒绝、成员权限、只读检查、重复配置和事务回滚。测试 cleanup 精确删除自身创建对象；失败时不忽略清理异常，不使用生产 DSN 默认值。
- 已执行的本地命令：`FIN_OPS_CASH_PROVISION_TEST_ADMIN_URL='postgresql://yu@localhost:5432/postgres' PYTHONPATH=backend/src python3 -m unittest tests.test_cash_postgres_permissions -v`。当前 12 项通过，包含真实受限CashRuntime/API完整创建/读取/删除链；元数据复查测试数据库与角色均无残留。该结果不等于生产授权验证。
- 生产验证只读，不为验收插入试验现金。完整本地链路、性能与发布结果见[实施记录](../dev/cash-module-implementation-plan.md)和[现金测试矩阵](../modules/cash/tests.md)。OA 真实字典读取必须使用有效登录会话；401 不能当作已验证通过或转换成空项目列表。
- 代理日志由管理员检查实际Nginx站点配置，不猜测线上location或修改普通请求日志。现金路径的query、具体ID与请求正文不得进入全局业务操作历史；应用/Gunicorn已脱敏为通用`/api/cash`，Nginx应采用同等脱敏或仅对现金请求关闭access记录，保留普通页面现有诊断。验证配置后执行`nginx -t`并在正常发布窗口应用。deploy账号无法读取配置时明确记录未验证，不能从示例文件宣称线上安全。
- 本工具不产生数据库备份，也不会删除主数据库。若发布流程产生任务专用备份，按既有[数据安全流程](data-safety.md)在确认完成后清理精确任务备份；不删除主库、永久 cash env 或现金业务表。
- 首次安装和复查完成后，管理员移除本次临时 provision 凭据文件并清除当前 shell 的三个 provision 输入变量；保留永久 API cash env。清理只针对已确认的临时文件，不使用宽泛目录删除。
- 代码回退不删除 `cash` schema、角色或业务记录。不能用旧代码访问现金池，也不能靠换成超级用户/普通 App DSN 让现金服务“先运行”。本次新增现金 schema 不要求改动既有业务表；其他历史 forward-only 迁移的回退限制仍适用。

权限/API事实见[现金边界](../modules/cash/boundary-io.md)；字段、事务和接口见[技术设计](../dev/cash-module-technical-design.md)。文档和工具交付不代表生产 root/DBA 配置已执行，最终应以发布记录中的实际结果为准。
