# Prompt 29：实现 OA 菜单 iframe 集成

目标：把 `fin-ops-platform` 作为一个可从 OA 菜单进入的内嵌子系统接入 OA 页面壳体，而不是独立页面体系。

前提：

- `28-oa-shell-auth-foundation.md` 已完成
- OA 前端源码路径：
  - `/Users/yu/Desktop/sy/smart-oa-ui`

要求：

- 基于 OA 现有 `InnerLink` 能力接入 `fin-ops-platform`
- 在 OA 菜单体系中新增一个入口，例如：
  - `财务运营平台`
- 入口目标为部署后的 `fin-ops` 页面地址
- 打开后在 OA 内容区 iframe 内显示
- 不破坏 OA 顶部导航、页签和左侧菜单
- 对 iframe 高度、加载、滚动条做最小必要适配

建议文件：

- `/Users/yu/Desktop/sy/smart-oa-ui/src/layout/components/InnerLink/index.vue`
- `/Users/yu/Desktop/sy/smart-oa-ui/src/layout/components/TopNav/index.vue`
- `/Users/yu/Desktop/sy/smart-oa-ui/src/store/modules/permission.js`
- 如需要，补充 OA 菜单配置或说明文档
- `docs/README.md`
- `prompts/README.md`

交付要求：

- OA 菜单能承载 fin-ops 页面
- 页面在 OA 中打开时布局稳定
- 不要求这一步完成权限封锁，但菜单结构必须为后续权限控制预留

验证：

- OA 前端本地或联调环境可打开内嵌页面
- 页面不会溢出 OA 可视区域

