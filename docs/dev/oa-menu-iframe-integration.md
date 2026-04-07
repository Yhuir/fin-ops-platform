# OA 菜单 iframe 集成说明

日期：2026-04-03

## 目标

把 `fin-ops-platform` 作为 OA 内嵌子系统接入 OA 页面壳体：

- OA 菜单项进入 `fin-ops`
- 页面在 OA 内容区 iframe 内显示
- `fin-ops` 在嵌入态隐藏自身全局头部，避免出现双重导航
- 前端构建支持部署到 `/fin-ops/` 子路径

## 推荐部署路径

- fin-ops 前端：`/fin-ops/`
- fin-ops 后端：`/fin-ops-api/`

推荐正式 iframe 地址：

- `https://oa.company.com/fin-ops/?embedded=oa`

其中 `embedded=oa` 用来强制启用嵌入壳模式。即使浏览器环境无法稳定识别 iframe，该参数也能确保 `fin-ops` 隐藏自己的全局头部。

## OA 菜单配置

该 OA 系统的菜单来源是数据库 `sys_menu`，不是前端写死路由。

建议在 OA 菜单管理中新增一个菜单：

- 菜单名称：`财务运营平台`
- 上级菜单：放在财务相关目录下
- 显示顺序：按现有财务菜单顺序插入
- 路由地址：`https://oa.company.com/fin-ops/?embedded=oa`
- 组件路径：留空
- 菜单类型：`C`
- 是否外链：`1`
- 是否缓存：`1`
- 是否新窗口打开：`1`
- 显示状态：`0`
- 菜单状态：`0`
- 权限标识：`finops:app:view`
- 图标：按 OA 现有图标体系选一个财务相关图标

原因：

- `isFrame = 1` 且 `path` 为 `http(s)` 时，OA 后端会把该菜单识别为 `InnerLink`
- `isBlank = 1` 表示不新开窗口，而是在 OA 内容区内嵌显示
- `finops:app:view` 为后续 Prompt 30 的强制权限封锁预留

## 可选菜单创建载荷

如果通过 OA 后端接口创建菜单，可参考以下字段结构：

```json
{
  "menuName": "财务运营平台",
  "parentId": 0,
  "orderNum": 90,
  "path": "https://oa.company.com/fin-ops/?embedded=oa",
  "component": "",
  "query": "",
  "isFrame": "1",
  "isCache": "1",
  "isBlank": "1",
  "menuType": "C",
  "visible": "0",
  "status": "0",
  "perms": "finops:app:view",
  "icon": "money"
}
```

`parentId` 和 `orderNum` 需要按实际 OA 菜单树调整。

仓库里也已放置模板文件：

- [fin_ops_menu_payload.json](/Users/yu/Desktop/fin-ops-platform/deploy/oa/fin_ops_menu_payload.json)

## 当前代码适配点

### fin-ops

- React app 支持嵌入态：
  - `?embedded=oa`
  - 或浏览器检测到在 iframe 中运行
- 嵌入态下会隐藏全局头部，只保留业务内容区
- Vite 构建支持通过 `VITE_APP_BASE_PATH` 部署到子路径，例如 `/fin-ops/`

### smart-oa-ui

- `InnerLink` 已去掉硬编码高度，改为按视口和实际顶部偏移动态计算
- iframe 容器会在窗口 resize 后重新同步高度
- 加载态仍然保留，不影响现有 OA 菜单与页签体系

## 联调检查项

- 进入 OA 后，点击 `财务运营平台`
- 页面在 OA 内容区打开，而不是新标签页
- `fin-ops` 不出现自己的全局导航头
- 页面底部不溢出 OA 可视区域
- 收起/展开 OA 左侧菜单后，iframe 高度仍稳定
- 刷新当前页签后，仍然停留在 `fin-ops`

## 注意事项

- 这一步只负责菜单和 iframe 壳体接入，不负责权限强封锁
- 真正的“少数账号可见 + 直接 URL 也禁止访问”由 Prompt 30 完成
- 如果生产环境不用同域部署，需要重新评估 token、cookie、iframe 和导出下载行为

进一步的同域部署、回滚和联调清单说明见：

- `deploy/oa/README.md`
- `deploy/oa/nginx.fin-ops.conf.example`
- `deploy/oa/fin_ops.env.example`
