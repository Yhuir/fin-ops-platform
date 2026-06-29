# Canonical Facts Macro-Wave Plan

日期：2026-06-28

## 目标

完成 PostgreSQL canonical facts 的模块化闭环：每类业务事实一个 owner，清楚 I/O，禁止旧事实源污染新链路，删除旧生产 source-of-truth 路径。

## Macro-Waves

1. `wave-1-contract-foundation`：建立 GSD 状态、长期 canonical facts 合同、模块入口和索引。
2. `wave-2-owner-boundary-io`：批量更新 owner 模块 `boundary-io.md`，写明 owned facts、允许写/读、downstream 输出和旧代码删除条件。
3. `wave-3-legacy-removal-inventory`：扫描旧生产 source-of-truth 路径，分类为 remove-now、blocked-by-owner-migration、tool-only-deferred。
4. `wave-4-static-guards`：为最危险旧路径补静态 guard 或 targeted tests，防止 full snapshot、state:*、direct cross-owner write 返回生产主链路。
5. `wave-5-code-removal`：按 owner 边界删除最高风险旧代码，不碰 07-owned read model runtime 文件。
6. `wave-6-final-audit`：生成 final closure report，列出 PSCF level、验证和剩余 blockers。

## 验收

- `docs/architecture/module-boundaries/canonical-facts.md` 存在并被索引。
- `docs/modules/canonical-facts/` 具备模块默认文件。
- 每个主要 fact family 有 owner。
- 每个 owner module 至少有 `boundary-io.md` 中的 canonical facts 条目。
- 旧生产 source-of-truth 路径被删除；无法删除的只作为 blocker/deferred，不算 closure。
- `bash scripts/verify.sh docs` 和 `git diff --check` 通过。
- 代码 wave 必须有 targeted tests。

## 非目标

- 不改 07 read model runtime 文件。
- 不新建集中式 runtime `UnifiedFactSource`。
- 不改变业务口径、API shape 或权限行为。
