# 后端重构生产就绪检查表

本文是 Axum + PostgreSQL 后端上线前门禁。每项必须有负责人、证据链接或执行记录；不能用口头确认代替。

## 使用方式

1. 在 staging 完成同版本验证。
2. 在生产变更单中逐项勾选并附证据。
3. 任一阻断条件存在时，停止上线或停止进入下一切换阶段。
4. 本检查表不授权生产切流；切流必须按 `cutover-and-rollback-runbook.md` 单独执行。

## 生产上线门禁

### 版本与配置

- [ ] Axum API、Python Worker、前端、migration 工具版本和 commit 已记录。
- [ ] 所有生产环境变量已有配置清单，清单不包含明文 secret。
- [ ] 启动配置缺失时服务会 fail fast，不以默认假值连接生产依赖。
- [ ] `/healthz`、`/readyz`、`/metrics` 已在 staging 验证。
- [ ] Nginx 路由、TLS、body limit、上传大小限制已在 staging 验证。
- [ ] 前端仍复用 OA 同域登录态，不引入独立登录绕过 OA 权限。

### Secret 管理

- [ ] PostgreSQL、Redis、NATS、MinIO/S3、OA session 接口等 secret 只存在于密钥管理系统或受控部署环境。
- [ ] git 中不存在密码、token、私钥、完整连接串、带签名 URL。
- [ ] 日志、错误响应、审计日志不会输出 secret。
- [ ] API、worker、migrator、readonly 使用不同 PostgreSQL 账号。
- [ ] MinIO/S3 访问账号按 API、worker、只读审计用途拆分。
- [ ] secret 轮换流程已记录，至少能轮换对象存储密钥和数据库账号密码。

### 权限与审计

- [ ] 后端通过 OA 会话接口识别当前用户，不信任前端菜单可见性。
- [ ] 未登录返回 `401`，无权限返回 `403`。
- [ ] 管理员能力仍按 `YNSYLP005` 等既有口径约束，不新增隐式超级用户。
- [ ] 导入确认、核销确认、撤回、异常处理、数据重置、权限设置写入审计事件。
- [ ] 审计事件包含操作者、时间、动作、参数摘要、结果和 trace id。
- [ ] 只读、导出、写操作、管理员能力已做权限测试。
- [ ] 高风险接口有幂等键或等价防重机制。

### 网络与 PostgreSQL 暴露面

- [ ] PostgreSQL 只监听 localhost 或内网地址，不开放公网。
- [ ] 云安全组、防火墙、`pg_hba.conf` 均不允许公网直连 PostgreSQL。
- [ ] API、worker、运维跳板机以外的来源不能访问 PostgreSQL。
- [ ] PostgreSQL 认证使用 SCRAM 或更强方式。
- [ ] PostgreSQL 账号最小权限已验证，readonly 不能写业务 schema。
- [ ] `/metrics` 仅允许内网或 Prometheus 采集端访问。
- [ ] NATS、Redis、MinIO 管理端不暴露公网，或只允许受控来源访问。

### 数据库与迁移

- [ ] `sqlx migrate run` 已在 staging 空库和带数据环境通过。
- [ ] 生产 migration 计划已经评估锁表风险。
- [ ] 大表 DDL 采用 expand/contract 或等价低风险方式。
- [ ] PostgreSQL 逻辑备份成功，备份文件可校验。
- [ ] PostgreSQL PITR 或等价时间点恢复方案已在 staging 演练通过。
- [ ] App Mongo 冻结点备份已完成并校验 checksum。
- [ ] App Mongo 恢复演练已完成，collection count 差异为 0 或已解释。
- [ ] 迁移对账报告显示核心对象数量、金额汇总和状态分布无无法解释差异。
- [ ] read model 可以从 PostgreSQL 事实表重建，不依赖手改缓存。

### Redis、NATS 和 Worker

- [ ] Redis 只存缓存、限流或短期进度，不存最终业务事实。
- [ ] Redis key 有 TTL 或明确生命周期。
- [ ] NATS stream、consumer、ack、retry、dead-letter 策略已在 staging 验证。
- [ ] outbox 发布失败可以重试，不丢业务事件。
- [ ] Worker 任务有状态、进度、失败原因、重试次数和 dead-letter 记录。
- [ ] 导入解析、OA 同步、read model 重建任务均可人工重放指定范围。
- [ ] Worker 写 PostgreSQL 失败不会静默成功。

### 文件与对象存储

- [ ] MinIO/S3 bucket 已启用版本化或有等价恢复策略。
- [ ] 上传文件校验扩展名、MIME、大小、行数和 checksum。
- [ ] 数据库只保存文件元数据、对象 key、checksum、大小和内容类型。
- [ ] GridFS 到 MinIO/S3 抽样 checksum 通过。
- [ ] 文件下载权限经过 OA 鉴权和业务权限校验。
- [ ] 导入文件、附件和导出文件的生命周期策略已确认。
- [ ] 病毒扫描或 OCR 风险已记录；未上线前不得把高风险文件处理伪装为已完成安全能力。

### 业务功能验证

- [ ] 导入预览、确认、重复提交、撤回在 staging 通过。
- [ ] 核销确认、撤回、异常处理、备注、忽略在 staging 通过。
- [ ] 单月工作台 read model 查询和全局搜索通过。
- [ ] 成本统计、税金抵扣、ETC、免 OA 批次的关键查询通过。
- [ ] OA 同步增量、水位、重试、指定范围重放通过。
- [ ] 数据重置或高风险运维操作只在授权环境验证，不在生产演练破坏性路径。

### 可观测性和告警

- [ ] API latency、4xx、5xx、in-flight、鉴权失败已有指标。
- [ ] PostgreSQL up、连接池、慢查询、deadlock、backup age、WAL archive lag 已有指标。
- [ ] Redis hit/miss、连接错误、内存、淘汰已有指标。
- [ ] NATS backlog、ack delay、redelivery、dead letter 已有指标。
- [ ] Worker success、failure、retry、duration、DB write failure 已有指标。
- [ ] MinIO/S3 upload/download error、checksum mismatch 已有指标。
- [ ] App Mongo 备份成功时间、恢复演练时间、checksum 状态已有指标或人工日报。
- [ ] read model stale、dirty scopes、重建失败已有指标。
- [ ] OA sync lag、同步失败、OA session 接口失败已有指标。
- [ ] P0/P1 告警已绑定值班人和升级路径。

### 性能与容量

- [ ] 关键接口在 staging 完成压测并记录 P50/P95/P99。
- [ ] 单月工作台 read model 命中达到当前目标。
- [ ] 全局搜索、导出和导入确认不阻塞主请求线程。
- [ ] PostgreSQL data、WAL、backup、logs 容量趋势已评估。
- [ ] 当前单机服务资源压力有监控，内存和磁盘不足时有告警。

### 切换与回滚

- [ ] 影子读、双写、切读、停止旧写的阶段方案已审阅。
- [ ] 读回滚路径已演练：前端或 Nginx/API route 可切回旧 Python。
- [ ] 写回滚路径已演练：双写差异可以暂停、补偿和重放。
- [ ] 文件回滚路径已演练：可从 MinIO/S3 版本或 GridFS 归档恢复。
- [ ] 切换窗口前后备份点已定义。
- [ ] 旧 Python 后端和 app Mongo 在回滚窗口内保留，不立即删除。
- [ ] PostgreSQL 成为事实源后，不允许用旧 Mongo 全量覆盖 PostgreSQL。

## 上线阻断条件

任一条件成立即阻断上线或阻断进入下一阶段：

| 阻断条件 | 原因 |
| --- | --- |
| App Mongo 备份缺失、checksum 失败或恢复演练未通过 | 无可靠回滚参考。 |
| PostgreSQL 备份或 PITR 演练未通过 | 新事实源不可恢复。 |
| PostgreSQL 需要公网开放才能被应用访问 | 违反生产网络底线。 |
| `pg_hba.conf`、防火墙或安全组允许不必要来源访问 PostgreSQL | 暴露面不可接受。 |
| 任一 secret 出现在 git、日志、告警样本或文档明文中 | 需要先清理和轮换。 |
| API/worker/migrator/readonly 账号未分离或 readonly 可写 | 最小权限不成立。 |
| 迁移对账存在无法解释的数量、金额或状态差异 | 业务事实不可信。 |
| GridFS 到 MinIO/S3 出现 checksum mismatch | 文件迁移不可信。 |
| read model 无法从事实表重建 | 切读后无法恢复页面口径。 |
| 核销确认、撤回、异常处理缺失审计日志 | 关键财务操作不可追溯。 |
| NATS dead letter、Worker 连续失败或 outbox 无法发布 | 异步链路不可靠。 |
| P0 告警未解除 | 继续切换会扩大故障面。 |
| 回滚路径未演练或旧 Python/app Mongo 已被提前移除 | 没有有效退路。 |
| 需要操作、备份、导出或修改 OA 源数据库才能上线 | 超出本项目授权边界。 |

## 上线通过记录模板

```text
change_id:
env:
api_commit:
worker_commit:
web_commit:
migration_version:
mongo_backup_id:
postgres_backup_id:
postgres_pitr_drill:
minio_checksum_sample:
migration_validation_report:
shadow_read_window:
dual_write_window:
rollback_drill_record:
approvers:
known_risks:
go_no_go:
```

## 回滚触发条件

上线后任一条件出现，应进入 `cutover-and-rollback-runbook.md` 对应回滚流程：

- P0 告警触发且 5 分钟内不能恢复。
- API 5xx 持续高于阈值并影响核心页面。
- 关键 read model stale 超过阈值，且旧读路径可用。
- 双写差异出现无法解释的金额或状态不一致。
- 文件 checksum mismatch。
- 核销确认、撤回、异常处理出现审计缺失或幂等失效。
- OA 同步滞后影响新数据可见性，且无法通过重试恢复。

## 剩余风险记录

每次上线必须在变更单记录剩余风险，包括：

- 未完成但接受的监控缺口。
- 未覆盖的业务样本。
- 未解决的容量风险。
- 仍需人工处理的补偿脚本。
- 回滚窗口结束时间和旧系统冻结计划。
