# 生产访问状态 2026-06-22

**目的:** 记录当前可用 SSH 能力，约束后续模块化 IO 重构的生产验证计划。
**结论:** 当前可以进入服务器，但只能做有限的非特权只读验证；还不能支撑完整生产验证闭环。

## 当前可用 SSH alias

| Alias | Host | User | Key | 状态 |
| --- | --- | --- | --- | --- |
| `finops-prod` | `139.155.5.132` | `finops-deploy` | `~/.ssh/finops_prod_ed25519` | 可登录 |
| `finops-prod-root` | `139.155.5.132` | `root` | `~/.ssh/finops_codex_tmp` | 不可登录，`Permission denied` |

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

## 当前可以做的生产验证

在 `finops-prod` 下可以做不需要 sudo、不会读取 secret、不会写生产状态的只读检查，例如：

- `hostname`、`whoami`、`date`。
- 非特权目录可见性检查。
- 如果部署目录、日志或 health endpoint 对 `finops-deploy` 可读，则可做相应只读探测。
- 通过公开 HTTP endpoint 做只读 smoke，但不能带生产 token/cookie。

## 当前不能保证完成的验证

在当前权限下，不能保证完成：

- 读取 `/etc/fin-ops/*.env` 或 secret env。
- 查看 root-only systemd unit / service journal。
- 重启服务、worker 或 deploy。
- 执行需要 root/`fin-ops` 组权限的 deploy readiness 检查。
- 连接生产 PostgreSQL，除非已有非 secret DSN 或服务器上有受控只读 wrapper。
- 检查真实 outbox/readiness/read model 表，除非提供只读 DB 入口。
- 执行任何生产写入验证。

## 仍缺的访问条件

要把生产验证推进到完整闭环，需要至少满足一种：

1. `finops-prod-root` 公钥登录可用。
2. `finops-deploy` 加入 `fin-ops` 组，并有足够只读权限读取非 secret 运行状态。
3. 为 `finops-deploy` 配置限定命令的 sudo，例如只允许 `systemctl status`、`journalctl -u <finops-unit>`、只读 health/check 脚本。
4. 提供服务器本地的只读验证脚本，由 root 管理 secret，脚本输出脱敏结果。
5. 提供 staging 或只读 PostgreSQL DSN。

## 安全规则

- 不把 SSH 密码、root 密码、数据库密码、token、cookie 或生产 DSN 写入 `.planning/`、`docs/`、脚本、测试、commit 或聊天。
- 生产写入验证必须单独审批，有备份、影响范围、回滚方案和维护窗口。
- 没有 root/sudo/只读 DB 时，模块状态不能从 `ProductionValidationPending` 进入 `Closed`。

