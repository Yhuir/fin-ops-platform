# 关联预览三栏 UI 开发拆分

## 需求范围

确认关联和撤回关联都必须先打开预览弹窗。弹窗里的“操作前 / 操作后”必须使用和关联台主三栏一致的视觉结构：OA 栏、流水栏、发票栏，行卡片、列头、空栏占位和金额高亮保持一致。预览只展示本次操作涉及的项，不展示全部关联台数据。

本次视觉层级优化进一步约定：金额核对信息从每个 pane 内的合计行上移到每个 section 顶部，形成独立“金额核对条”。二次简化后，顶部 summary 不再呈现三张 metric 卡片，而是一行紧凑金额核对摘要：左侧保留“金额核对”语义，中间依次展示 OA、流水、发票金额，右侧在不一致时以 pill/block 展示 `差额 2,307.12` 这类简洁文案，不展示 `差额：OA - 流水 = 2,307.12` 公式。数量只在 pane header 展示，金额核对条不展示 `n 项`。三栏 pane 表头只保留栏名和数量，避免 `OA合计 / 流水合计 / 发票合计` 与列头、行内容混杂。操作前和操作后使用不同浅背景 tone class（如 `relation-preview-section-before` / `relation-preview-section-after`）和更明确的分隔线，增强变更前后对比感。

确认关联时，操作前应表达当前状态：没有旧关系的选中项分别在不同行；已有旧关系的项按旧关系同行展示，其余新加入项单独展示。操作后应表达本次确认后的目标关系：被确认关联的项进入同一行。

撤回关联时，操作前应展示当前已关联关系在同一行。操作后应展示撤回后的上一层关系：如果原先 OA+发票已配对，撤回三方关系后 OA+发票仍同行，流水单独回到未配对；如果没有可恢复关系，则受影响项拆回单独行。

## UI 优化验收点

- `relation-preview-before` 和 `relation-preview-after` 外层 section 继续保留，两个 section 内都必须包含 `relation-preview-summary` 和 `tri-pane`。
- 操作前 / 操作后 section 应有可测试的不同浅背景 class，例如 `relation-preview-section-before` 和 `relation-preview-section-after`。
- `relation-preview-summary` 内稳定暴露 `relation-preview-summary-metric-oa`、`relation-preview-summary-metric-bank`、`relation-preview-summary-metric-invoice`，并保留 `金额核对` 文案；summary 只展示金额，不展示数量。
- 金额可计算且不一致时显示 `relation-preview-delta`；差额文案使用 `差额 2,307.12` 这类简洁格式，不展示 OA / 流水 / 发票之间的公式表达。
- 不一致的 metric 使用 `mismatch` 或 `relation-preview-summary-metric-mismatch` 高亮类。高亮按金额分组而非机械后端字段：两栏可比较且金额不同，两栏都高亮；三栏中两栏一致一栏不同，只高亮孤立金额；三栏金额都不同，全高亮；缺失金额不参与分组和高亮。
- `pane-oa`、`pane-bank`、`pane-invoice` 继续保留，pane header 只展示栏名和数量，不再承载 `OA合计 / 流水合计 / 发票合计`。
- `candidate-group-*` 和只读行卡片结构继续保留，用于证明操作前拆分、操作后合并或恢复上一层关系。
- 备注输入框测试继续使用 `role="textbox"` 和 `name="备注"` 定位，避免与三栏中的“备注”列头冲突。

## 子任务 Prompt A：三栏只读预览组件

你是负责前端组件实现的 Codex 子代理。请在 `/Users/yu/Desktop/fin-ops-platform` 完成以下任务：

1. 新建 `web/src/components/workbench/RelationPreviewTriPane.tsx`。
2. 组件输入：
   - `title: string`
   - `testId?: string`
   - `groups: WorkbenchCandidateGroup[]`
   - `totals: { oaTotal: string; bankTotal: string; invoiceTotal: string }`
   - `mismatchFields: string[]`
   - `columnLayouts?: WorkbenchColumnLayouts`
3. 复用关联台现有样式和渲染基础：
   - 使用 `getWorkbenchColumns` 和 `getWorkbenchPaneGridStyle` 保持列配置一致。
   - 使用 `CandidateGroupCell` 和 `WorkbenchRecordCard` 保持行卡片一致。
   - 三栏固定为 OA、流水、发票。
   - 空栏显示 `-`。
4. 组件必须是只读：
   - 行点击、详情、行内操作都不触发业务行为。
   - 不显示主关联台里的确认、撤回、详情操作按钮。
   - 不显示搜索、排序、筛选、列拖拽等操作控件。
5. 金额核对和高亮：
   - 每个 section 顶部显示独立一行金额核对摘要，包含 `金额核对`、OA 金额、流水金额、发票金额。
   - summary metric 仅展示金额，不展示 `n 项`；数量只出现在 pane header。
   - pane header 只显示栏名和数量，不在 pane 内显示 `OA合计`、`流水合计`、`发票合计`。
   - 金额不一致时以 `relation-preview-delta` 展示简洁差额 pill/block，例如 `差额 2,307.12`，不展示公式。
   - metric 高亮按金额分组计算：两栏不同都高亮；三栏两同一异只高亮孤立项；三栏全不同全高亮；缺失金额不参与。
6. 增加稳定测试定位：
   - 外层 section 支持 `testId`。
   - 三栏容器使用 `data-testid="tri-pane"`。
   - 三个 pane 使用 `pane-oa`、`pane-bank`、`pane-invoice`。
   - 每个 group 使用 `candidate-group-${group.id}`。
7. 如现有 `CandidateGroupCell` / `WorkbenchRecordCard` 缺少只读入口，可以最小化增加 `readOnly?: boolean`，默认值必须保持现有行为不变。
8. 不接入页面，不改测试，由主线程负责集成和验证。

## 子任务 Prompt B：测试与风险分析

你是负责测试设计的 Codex 子代理。请只读分析，不修改文件。目标是给出必须更新的测试点和可能遗漏的 mock 情况：

1. 阅读 `web/src/test/WorkbenchSelection.test.tsx`、`web/src/test/apiMock.ts` 和关联台组件。
2. 找出当前依赖简化预览列表的断言，例如只检查 `OA合计` / `流水合计` / `发票合计` 的测试。
3. 给出新的断言建议：
   - 预览弹窗内有 `relation-preview-before` 和 `relation-preview-after`。
   - 操作前 / 操作后 section 有不同浅背景相关 class。
   - 两个 section 内都包含 `tri-pane` 和三个 pane。
   - 两个 section 内都包含一行 `relation-preview-summary`，summary 内有 `金额核对` 和三类金额 metric，但不包含 `n 项` 数量。
   - 确认关联操作前多组、操作后一组。
   - 撤回关联操作前一组、操作后保留上一层关系或拆回单独行。
   - 弹窗内不出现未选中的无关项。
   - 金额不一致时存在 `relation-preview-delta`，文案包含 `差额`，但不匹配 `OA -`、`流水 -`、`发票 -` 等公式片段。
4. 检查 mock 是否能证明“操作前不同行、操作后同行”。如果现有 mock 选中项本来已经同 case，需要建议调整 mock。
5. 检查撤回预览是否能证明“恢复上一层关系”。如果接口 mock 没返回或前端没消费 restored relation，需要指出风险。

## 主线程集成任务

1. 在 `ReconciliationWorkbenchPage.tsx` 中用 `RelationPreviewTriPane` 替换旧的 `RelationPreviewSection` / `RelationPreviewPane` 简化 UI。
2. 把 `workbenchSettings.workbenchColumnLayouts` 传给预览组件，保持列顺序和主关联台一致。
3. 修改后端 `_relation_groups`：
   - 支持把未被旧关系覆盖的选中项拆成单独组。
   - 确认预览的操作前使用拆分模式。
   - 撤回预览的操作后同时展示恢复关系和被撤回后落单的项。
4. 修改前端 mock：
   - 确认预览：操作前选中项分别成组，操作后同组。
   - 撤回预览：操作前同组，操作后恢复旧关系并保留落单项。
5. 更新测试：
   - 关联预览使用三栏结构断言，不再只依赖合计文案。
   - 补充确认/撤回预览的 before/after group 数量和行卡片样式断言。
   - 补充 before/after section 顶部金额核对摘要断言：`relation-preview-summary`、`金额核对` 文案及 OA / 流水 / 发票三个金额 metric 都存在；summary 不包含数量。
   - 补充 before/after section 浅背景 class 断言：`relation-preview-section-before` / `relation-preview-section-after` 或最终实现采用的等价稳定 class。
   - 补充金额不一致断言：弹窗提示金额不一致，按金额分组规则高亮 metric，并在可计算时展示 `relation-preview-delta`；delta 文案应包含 `差额` 且不包含公式片段。
   - 确认 pane header 仍存在但只承载栏名和数量，测试不再依赖 pane 内旧合计行。
   - 金额不一致备注输入框按 `textbox` 定位，避免和三栏里的“备注”列头冲突。
6. 验证：
   - 后端关联预览测试。
   - `WorkbenchSelection.test.tsx`。
   - 相关后端/frontend targeted tests。
   - `npm run build`。
