import { Button, Checkbox, Input } from "@heroui/react";

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
  displayName: string;
  selectedCodes: string[];
  loading: boolean;
  saving: boolean;
  interactionLocked: boolean;
  error: string | null;
  canSave: boolean;
  onDisplayNameChange: (value: string) => void;
  onToggleCode: (code: string) => void;
  onToggleGroup: (codes: string[], checked: boolean) => void;
  onClose: () => void;
  onSave: () => void;
};

function groupTags(tags: CostStatisticsTagRuleTag[]): TagGroup[] {
  const groups = new Map<string, TagGroup>();
  for (const tag of tags) {
    const primary = tag.path[0] || tag.outputPrimaryLabel || tag.label || "未分类";
    const directionLabel = tag.direction === "income" ? "收入" : tag.direction === "expense" ? "支出" : "收支共用";
    const key = `${tag.direction}:${primary}`;
    const group = groups.get(key) ?? { key, label: `${directionLabel} · ${primary}`, tags: [] };
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
  displayName,
  selectedCodes,
  loading,
  saving,
  interactionLocked,
  error,
  canSave,
  onDisplayNameChange,
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
      ariaBusy={saving || loading || interactionLocked}
      className="cost-tag-rules-drawer"
      closeDisabled={saving}
      footer={(
        <div className="cost-tag-rules-footer" inert={interactionLocked ? true : undefined}>
          <div className="cost-tag-rules-footer-status" role="status">
            {rules ? `已选 ${selectedCount} / ${tagCount}` : ""}
          </div>
          <div className="cost-tag-rules-footer-actions">
            <Button className="cost-drawer-secondary-button" isDisabled={saving || interactionLocked} onPress={onClose} size="sm" variant="secondary">
              取消
            </Button>
            <Button
              className="cost-drawer-primary-button"
              isDisabled={!rules || loading || saving || interactionLocked || !canSave || (selectedCodes.length > 0 && !displayName.trim())}
              isPending={saving}
              onPress={onSave}
              size="sm"
              variant="primary"
            >
              保存
            </Button>
          </div>
        </div>
      )}
      onClose={onClose}
      open={open}
      title="无 OA 成本范围"
      width={460}
    >
      <div className="cost-tag-rules-body" inert={interactionLocked ? true : undefined}>
        {loading ? <div className="cost-tag-rules-state">正在加载标签规则...</div> : null}
        {error ? <div className="cost-tag-rules-state error">{error}</div> : null}
        {!loading && rules ? (
          <>
            <div className="cost-tag-rules-intro">
              这里只列出当前确实存在无 OA 关系的支出流水标签。纳入时仍逐笔判断；同一标签下已有 OA 关系的流水不会进入虚拟项目。
            </div>
            <Input
              aria-label="无 OA 虚拟项目名称"
              className="cost-tag-rules-name"
              disabled={saving || interactionLocked}
              maxLength={80}
              onChange={(event) => onDisplayNameChange(event.currentTarget.value)}
              placeholder="由用户填写，例如：云南溯源无 OA 分类"
              value={displayName}
            />
            <div className="cost-tag-rules-list" role="group" aria-label="无 OA 成本标签选择">
              {groups.length === 0 ? (
                <div className="cost-tag-rules-state">当前没有带标签的无 OA 支出流水。</div>
              ) : groups.map((group) => {
              const codes = group.tags.map((tag) => tag.code);
              const checkedCount = codes.filter((code) => selectedSet.has(code)).length;
              const checked = checkedCount === codes.length && codes.length > 0;
              const indeterminate = checkedCount > 0 && checkedCount < codes.length;
              return (
                <section className="cost-tag-rules-group" key={group.key}>
                  <Checkbox
                    className="cost-tag-rules-main"
                    isDisabled={saving || interactionLocked}
                    isIndeterminate={indeterminate}
                    isSelected={checked}
                    onChange={(selected) => onToggleGroup(codes, selected)}
                  >
                    <Checkbox.Control><Checkbox.Indicator /></Checkbox.Control>
                    <span>{group.label}</span>
                    <em>{checkedCount}/{codes.length}</em>
                  </Checkbox>
                  <div className="cost-tag-rules-children">
                    {group.tags.map((tag) => (
                      <Checkbox
                        className="cost-tag-rules-child"
                        isDisabled={saving || interactionLocked}
                        isSelected={selectedSet.has(tag.code)}
                        key={tag.code}
                        onChange={() => onToggleCode(tag.code)}
                      >
                        <Checkbox.Control><Checkbox.Indicator /></Checkbox.Control>
                        <span>{tagLeafLabel(tag)}</span>
                      </Checkbox>
                    ))}
                  </div>
                </section>
              );
              })}
            </div>
          </>
        ) : null}
      </div>
    </AppDrawer>
  );
}
