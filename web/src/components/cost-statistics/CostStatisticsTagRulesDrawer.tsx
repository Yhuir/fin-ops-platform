import AppDrawer from "../common/AppDrawer";
import type { CostStatisticsTagRuleTag, CostStatisticsTagRules } from "../../features/cost-statistics/types";

type TagGroup = {
  key: string;
  label: string;
  tags: CostStatisticsTagRuleTag[];
};

type CostStatisticsTagRulesDrawerProps = {
  open: boolean;
  rules: CostStatisticsTagRules | null;
  selectedCodes: string[];
  loading: boolean;
  saving: boolean;
  error: string | null;
  syncMessage: string | null;
  canSave: boolean;
  onToggleCode: (code: string) => void;
  onToggleGroup: (codes: string[], checked: boolean) => void;
  onClose: () => void;
  onSave: () => void;
};

function groupTags(tags: CostStatisticsTagRuleTag[]): TagGroup[] {
  const groups = new Map<string, TagGroup>();
  for (const tag of tags) {
    const primary = tag.path[0] || tag.outputPrimaryLabel || tag.label || "未分类";
    const key = primary;
    const group = groups.get(key) ?? { key, label: primary, tags: [] };
    group.tags.push(tag);
    groups.set(key, group);
  }
  return Array.from(groups.values()).map((group) => ({
    ...group,
    tags: [...group.tags].sort((left, right) => tagLeafLabel(left).localeCompare(tagLeafLabel(right), "zh-CN")),
  }));
}

function tagLeafLabel(tag: CostStatisticsTagRuleTag) {
  return tag.path[1] || tag.outputSubLabel || tag.label || tag.code;
}

export default function CostStatisticsTagRulesDrawer({
  open,
  rules,
  selectedCodes,
  loading,
  saving,
  error,
  syncMessage,
  canSave,
  onToggleCode,
  onToggleGroup,
  onClose,
  onSave,
}: CostStatisticsTagRulesDrawerProps) {
  const selectedSet = new Set(selectedCodes);
  const groups = groupTags(rules?.activeTags ?? []);
  const selectedCount = groups.reduce(
    (count, group) => count + group.tags.filter((tag) => selectedSet.has(tag.code)).length,
    0,
  );
  const tagCount = groups.reduce((count, group) => count + group.tags.length, 0);

  return (
    <AppDrawer
      ariaBusy={saving || loading}
      className="cost-tag-rules-drawer"
      closeDisabled={saving}
      footer={(
        <div className="cost-tag-rules-footer">
          <div className="cost-tag-rules-footer-status" role="status">
            {syncMessage || (rules ? `已选 ${selectedCount} / ${tagCount}` : "")}
          </div>
          <div className="cost-tag-rules-footer-actions">
            <button className="cost-drawer-secondary-button" disabled={saving} onClick={onClose} type="button">
              取消
            </button>
            <button
              className="cost-drawer-primary-button"
              disabled={!rules || loading || saving || !canSave}
              onClick={onSave}
              type="button"
            >
              {saving ? "保存并同步中" : "保存并同步"}
            </button>
          </div>
        </div>
      )}
      onClose={onClose}
      open={open}
      subtitle={rules ? `银行标签版本 ${rules.bankAutoTagRulesVersion}` : "读取银行标签中"}
      title="成本统计标签规则"
      width={460}
    >
      {loading ? <div className="cost-tag-rules-state">正在加载标签规则...</div> : null}
      {error ? <div className="cost-tag-rules-state error">{error}</div> : null}
      {!loading && rules ? (
        <div className="cost-tag-rules-list" role="group" aria-label="成本统计标签选择">
          {groups.map((group) => {
            const codes = group.tags.map((tag) => tag.code);
            const checkedCount = codes.filter((code) => selectedSet.has(code)).length;
            const checked = checkedCount === codes.length && codes.length > 0;
            const indeterminate = checkedCount > 0 && checkedCount < codes.length;
            return (
              <section className="cost-tag-rules-group" key={group.key}>
                <label className="cost-tag-rules-main">
                  <input
                    checked={checked}
                    data-indeterminate={indeterminate ? "true" : undefined}
                    disabled={saving}
                    onChange={(event) => onToggleGroup(codes, event.currentTarget.checked)}
                    type="checkbox"
                  />
                  <span>{group.label}</span>
                  <em>{checkedCount}/{codes.length}</em>
                </label>
                <div className="cost-tag-rules-children">
                  {group.tags.map((tag) => (
                    <label className="cost-tag-rules-child" key={tag.code}>
                      <input
                        checked={selectedSet.has(tag.code)}
                        disabled={saving}
                        onChange={() => onToggleCode(tag.code)}
                        type="checkbox"
                      />
                      <span>{tagLeafLabel(tag)}</span>
                    </label>
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      ) : null}
    </AppDrawer>
  );
}
