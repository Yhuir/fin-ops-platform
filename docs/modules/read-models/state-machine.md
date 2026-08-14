# Read Model 退役状态机

```text
active legacy runtime -> code/config retired -> migration 0149 applied -> forbidden
```

`forbidden` 是终态。Migration 0149 后禁止自动回到依赖旧 schema 的 release。
