# 生产访问状态 2026-06-22

**目的:** 记录当前可用 SSH 能力，约束后续模块化 IO 重构的生产验证计划。
**结论:** 当前可以通过 `finops-prod-root` 免密公钥登录服务器 root 用户；可支持特权只读生产验证。生产写入、读取 secret、数据库写入、worker 消费/重放仍必须单独审批。

**更新:** 2026-06-23 已完成 root 公钥安装，验证 `ssh finops-prod-root` 成功返回 `user=root uid=0 host=VM-0-6-opencloudos key_login=ok`。

## 当前可用 SSH alias

| Alias | Host | User | Key | 状态 |
| --- | --- | --- | --- | --- |
| `finops-prod` | `139.155.5.132` | `finops-deploy` | `~/.ssh/finops_prod_ed25519` | 可登录 |
| `finops-prod-root` | `139.155.5.132` | `root` | `~/.ssh/finops_codex_tmp` | 可免密公钥登录 |

## 已验证结果

`ssh finops-prod 'hostname && whoami'` 成功：

```text
VM-0-6-opencloudos
finops-deploy
```

`finops-deploy` 权限状态：

```text
uid=1002(finops-deploy) gid=1002(finops-deploy) groups=1002(finops-deploy)
SUDO_NOPASSWD_NO
```

关键目录权限示例：

```text
/etc/fin-ops -> root:fin-ops 750
```

`ssh finops-prod-root` 成功：

```text
user=root uid=0 host=VM-0-6-opencloudos key_login=ok
```

root 公钥安装时发现 `/root/.ssh/authorized_keys` 带有 `immutable + append-only` 文件属性；已临时解除属性、追加公钥、恢复权限和 `+i +a` 属性，并通过 `sshd -t` 与 `systemctl reload sshd`。

## 当前可以做的生产验证

在 `finops-prod` 下可以做不需要 sudo、不会读取 secret、不会写生产状态的只读检查，例如：

- `hostname`、`whoami`、`date`。
- 非特权目录可见性检查。
- 如果部署目录、日志或 health endpoint 对 `finops-deploy` 可读，则可做相应只读探测。
- 通过公开 HTTP endpoint 做只读 smoke，但不能带生产 token/cookie。

在 `finops-prod-root` 下可以做特权只读检查，例如：

- `systemctl status <unit>`。
- `journalctl -u <unit>` 的脱敏只读摘录。
- 部署目录、systemd unit、worker/readiness 文件权限检查。
- root-only health/readiness 脚本的 dry-run 或 read-only 模式。

即使具备 root，也不得在自动重构流程中读取、打印或提交 secret 值。

## 当前不能保证完成的验证

即使 root 免密可用，仍不能自动完成或默认允许：

- 读取或输出 `/etc/fin-ops/*.env`、secret env、token、cookie 或生产 DSN。
- 重启服务、worker 或 deploy。
- 写业务表、改 readiness、消费/重放 outbox 或 dirty scope。
- 连接生产 PostgreSQL，除非服务器上已有受控只读 wrapper，且输出脱敏。
- 执行任何生产写入验证。

## 仍缺的访问条件

要把生产验证推进到完整闭环，仍需要按模块准备：

1. root 可执行的只读验证命令清单。
2. 输出脱敏规则。
3. 对 PostgreSQL/read model/worker 的受控只读 wrapper，避免暴露 DSN 或 secret。
4. 任何生产写入验证的审批、备份、影响范围、回滚方案和维护窗口。

## 安全规则

- 不把 SSH 密码、root 密码、数据库密码、token、cookie 或生产 DSN 写入 `.planning/`、`docs/`、脚本、测试或 commit。
- 生产写入验证必须单独审批，有备份、影响范围、回滚方案和维护窗口。
- 没有受控只读 DB/read model/worker 证据时，相关模块状态不能从 `ProductionValidationPending` 进入 `Closed`。
