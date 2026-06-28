# 部署架构

## 当前部署形态

当前推荐 OA 同域部署：

```text
https://oa.company.com/fin-ops/      -> React 前端
https://oa.company.com/fin-ops-api/  -> Python 后端
```

详细部署步骤、Nginx 示例、环境变量和 OA 菜单 SQL 见 `../../deploy/oa/README.md`。

## 组件

- Nginx：路径转发、静态资源、API 反代。
- 后端进程：Python app server。
- Worker 进程：PostgreSQL durable queue consumer，负责 OA sync、导入处理、文件迁移、Workbench matching 和受控修复任务。
- 前端构建产物：Vite build 输出。
- PostgreSQL：app 事实、设置、队列、审计、健康状态和历史迁移表。
- MinIO/S3：文件对象。
- Redis：短 TTL cache、wakeup 和辅助锁；不可用时 PostgreSQL polling 仍可运行。
- OA MongoDB：worker 只读源数据，不在 API 请求路径访问。
- OA 系统：登录、菜单、权限和 iframe 容器。

## 环境变量

部署环境变量集中在 `deploy/oa/fin_ops.env.example`。生产环境不要把真实密钥提交到仓库。

## 发布顺序

1. 备份或确认可回滚点。
2. 发布后端。
3. 发布前端。
4. 同步 OA 菜单和角色。
5. 执行联调验收。
6. 观察 app health 和后台任务状态。

## 验收

- `/health` 可用。
- `/api/session/me` 能识别 OA token。
- 未授权账户返回 `403`。
- 只读导出账户无写入口且 API 拒绝写操作。
- 工作台、导入、税金、成本统计、银行明细、设置页可进入。
