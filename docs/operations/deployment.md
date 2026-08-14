# 生产部署

生产唯一入口：

```bash
./scripts/deploy-oa.sh
```

部署采用 immutable versioned release、原子 current symlink、systemd API/worker 和受控 root helper。当前 runtime
只有四个 worker，页面全部 direct canonical read。完整路径、环境、激活、forward-only migration、验证和恢复
规则见 [`../../deploy/oa/README.md`](../../deploy/oa/README.md)。

## 最小闭环

1. 本地 lint、backend、frontend、docs、build 与 diff check。
2. 提交并推送 remote `main`。
3. build/upload/候选校验。
4. maintenance 内 migration 与 exact runtime asset activation。
5. T+0/T+30 health、worker、queue、canonical audit 和 HTTP SLO。
6. 保存脱敏 evidence；成功后清理 release 临时文件。

Migration 0149 删除旧 projection schema，是 forward-only。执行后禁止自动回滚到依赖旧 schema 的 release；
失败时保持 maintenance 并用当前代码向前修复。不会删除主数据库。
