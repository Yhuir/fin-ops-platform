# 导入中心状态

- 页面：`loading -> ready | empty | error`；刷新只重读当前 tab 和页码。
- Tab：`files | batches`，切换后页码回到 1。
- 本模块没有业务写状态；文件、批次和 worker 状态均来自既有导入事实。
