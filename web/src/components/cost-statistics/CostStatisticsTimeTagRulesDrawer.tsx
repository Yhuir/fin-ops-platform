import { Button, Checkbox } from "@heroui/react";

import AppDrawer from "../common/AppDrawer";
import type {
  CostStatisticsTagRuleTag,
  CostStatisticsTimeTagRules,
} from "../../features/cost-statistics/types";

type Props = {
  open: boolean;
  rules: CostStatisticsTimeTagRules | null;
  mode: "all" | "custom";
  selectedCodes: string[];
  loading: boolean;
  saving: boolean;
  interactionLocked: boolean;
  error: string | null;
  canSave: boolean;
  onChange: (mode: "all" | "custom", codes: string[]) => void;
  onClose: () => void;
  onSave: () => void;
};

function leafLabel(tag: CostStatisticsTagRuleTag) {
  return tag.path[1] || tag.outputSubLabel || tag.label || tag.code;
}

function groupTags(tags: CostStatisticsTagRuleTag[]) {
  const groups = new Map<string, { key: string; label: string; tags: CostStatisticsTagRuleTag[] }>();
  for (const tag of tags) {
    const direction = tag.direction === "income" ? "收入" : tag.direction === "expense" ? "支出" : "不限";
    const primary = tag.path[0] || tag.outputPrimaryLabel || tag.label || "未分类";
    const key = `${direction}:${primary}`;
    const group = groups.get(key) ?? { key, label: `${direction} · ${primary}`, tags: [] };
    group.tags.push(tag);
    groups.set(key, group);
  }
  return [...groups.values()].map((group) => ({
    ...group,
    tags: group.tags.sort((left, right) => leafLabel(left).localeCompare(leafLabel(right), "zh-CN")),
  }));
}

export default function CostStatisticsTimeTagRulesDrawer({
  open,
  rules,
  mode,
  selectedCodes,
  loading,
  saving,
  interactionLocked,
  error,
  canSave,
  onChange,
  onClose,
  onSave,
}: Props) {
  const tags = rules?.availableTags ?? [];
  const allCodes = tags.map((tag) => tag.code);
  const selectedSet = new Set(mode === "all" ? allCodes : selectedCodes);
  const groups = groupTags(tags);

  function toggleCode(code: string) {
    const next = new Set(selectedSet);
    if (next.has(code)) next.delete(code); else next.add(code);
    onChange("custom", [...next]);
  }

  function toggleGroup(codes: string[], checked: boolean) {
    const next = new Set(selectedSet);
    for (const code of codes) {
      if (checked) next.add(code); else next.delete(code);
    }
    onChange(next.size === allCodes.length ? "all" : "custom", [...next]);
  }

  return (
    <AppDrawer
      ariaBusy={saving || loading || interactionLocked}
      className="cost-tag-rules-drawer"
      closeDisabled={saving}
      footer={(
        <div className="cost-tag-rules-footer" inert={interactionLocked ? true : undefined}>
          <div className="cost-tag-rules-footer-status" role="status">
            {rules ? `已选 ${selectedSet.size} / ${allCodes.length}` : ""}
          </div>
          <div className="cost-tag-rules-footer-actions">
            <Button isDisabled={saving || interactionLocked} onPress={onClose} size="sm" variant="secondary">取消</Button>
            <Button isDisabled={!rules || loading || saving || interactionLocked || !canSave} isPending={saving} onPress={onSave} size="sm" variant="primary">保存</Button>
          </div>
        </div>
      )}
      onClose={onClose}
      open={open}
      title="按标签/按时间标签规则"
      width={480}
    >
      <div className="cost-tag-rules-body" inert={interactionLocked ? true : undefined}>
        {loading ? <div className="cost-tag-rules-state">正在加载银行流水标签...</div> : null}
        {error ? <div className="cost-tag-rules-state error">{error}</div> : null}
        {!loading && rules ? (
          <>
            <div className="cost-tag-rules-intro">仅影响“按标签”和“按时间”。默认全选，后续新增标签也会自动纳入；收入、支出和未标记流水均可独立控制。</div>
            <div className="cost-tag-rules-toolbar">
              <Button isDisabled={!canSave || saving || interactionLocked} onPress={() => onChange("all", [])} size="sm" variant="secondary">全选</Button>
              <Button isDisabled={!canSave || saving || interactionLocked} onPress={() => onChange("custom", [])} size="sm" variant="secondary">清空</Button>
              <span>{mode === "all" ? "当前：全部标签（自动包含新标签）" : "当前：自定义范围"}</span>
            </div>
            <div aria-label="按标签和按时间统计范围" className="cost-tag-rules-list" role="group">
              {groups.map((group) => {
                const codes = group.tags.map((tag) => tag.code);
                const count = codes.filter((code) => selectedSet.has(code)).length;
                return (
                  <section className="cost-tag-rules-group" key={group.key}>
                    <Checkbox
                      className="cost-tag-rules-main"
                      isDisabled={!canSave || saving || interactionLocked}
                      isIndeterminate={count > 0 && count < codes.length}
                      isSelected={count === codes.length && codes.length > 0}
                      onChange={(selected) => toggleGroup(codes, selected)}
                    >
                      <Checkbox.Control><Checkbox.Indicator /></Checkbox.Control>
                      <span>{group.label}</span><em>{count}/{codes.length}</em>
                    </Checkbox>
                    <div className="cost-tag-rules-children">
                      {group.tags.map((tag) => (
                        <Checkbox className="cost-tag-rules-child" isDisabled={!canSave || saving || interactionLocked} isSelected={selectedSet.has(tag.code)} key={tag.code} onChange={() => toggleCode(tag.code)}>
                          <Checkbox.Control><Checkbox.Indicator /></Checkbox.Control>
                          <span>{leafLabel(tag)}</span>
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
