import { Button, Chip, ListBox, Select, Tabs } from "@heroui/react";
import { Plus, X } from "lucide-react";
import { useState } from "react";

import type { SettingsPendingInvoiceTagsSectionProps } from "./types";

const GROUP_LABELS: Record<SettingsPendingInvoiceTagsSectionProps["activeGroup"], string> = {
  requiresInvoice: "需要开票",
  bankStatementAsInvoice: "流水代替发票",
  noInvoiceRequired: "无需开票",
};

export default function SettingsPendingInvoiceTagsSection({
  activeGroup,
  controlsDisabled,
  groups,
  tags,
  onAddExistingTag,
  onRemoveTag,
  onSelectGroup,
}: SettingsPendingInvoiceTagsSectionProps) {
  const [selectedTagCode, setSelectedTagCode] = useState("");
  const activeTags = groups[activeGroup];
  const activeTagSet = new Set(activeTags);
  const tagsByCode = new Map(tags.map((tag) => [tag.code, tag]));
  const activeDefinitions = activeTags.map((code) => {
    const tag = tagsByCode.get(code);
    if (!tag) {
      return {
        code,
        label: code,
        path: [] as string[],
        status: "missing",
        issueLabel: "标签不存在",
      };
    }
    if (tag.status === "archived") {
      return {
        ...tag,
        issueLabel: "标签已停用",
      };
    }
    return {
      ...tag,
      issueLabel: null,
    };
  });
  const availableTags = tags.filter((tag) => tag.status === "active" && !activeTagSet.has(tag.code));

  function addExistingTag() {
    if (!selectedTagCode) return;
    onAddExistingTag(selectedTagCode);
    setSelectedTagCode("");
  }

  return (
    <section
      aria-labelledby="settings-section-pending-invoice-tags-title"
      className="settings-section-panel settings-section-panel--standard"
      id="settings-section-pending-invoice-tags"
      role="region"
    >
      <header className="settings-section-header">
        <h3 id="settings-section-pending-invoice-tags-title">待找发票筛选</h3>
      </header>
      <div className="settings-section-body">
        <Tabs
          className="settings-pending-tabs"
          selectedKey={activeGroup}
          variant="secondary"
          onSelectionChange={(key) => onSelectGroup(String(key) as typeof activeGroup)}
        >
          <Tabs.List aria-label="待找发票筛选分组">
            {(Object.keys(GROUP_LABELS) as Array<keyof typeof GROUP_LABELS>).map((group) => (
              <Tabs.Tab id={group} key={group}>
                {GROUP_LABELS[group]} {groups[group].length}
              </Tabs.Tab>
            ))}
          </Tabs.List>
        </Tabs>

        <div className="settings-pending-tag-toolbar">
          <label className="settings-field settings-field--tag-select">
            <span>已有标签</span>
            <Select
              aria-label="已有标签"
              isDisabled={controlsDisabled || availableTags.length === 0}
              selectedKey={selectedTagCode || null}
              onSelectionChange={(key) => setSelectedTagCode(String(key))}
            >
              <Select.Trigger>
                <Select.Value>
                  {({ isPlaceholder, selectedText }) => isPlaceholder ? "选择标签" : selectedText}
                </Select.Value>
                <Select.Indicator />
              </Select.Trigger>
              <Select.Popover>
                <ListBox>
                  {availableTags.map((tag) => (
                    <ListBox.Item id={tag.code} key={tag.code} textValue={tag.label}>
                      {tag.label}
                    </ListBox.Item>
                  ))}
                </ListBox>
              </Select.Popover>
            </Select>
          </label>
          <Button
            isDisabled={controlsDisabled || !selectedTagCode}
            variant="secondary"
            onPress={addExistingTag}
          >
            <Plus aria-hidden="true" size={16} />
            添加标签
          </Button>
        </div>

        <div className="settings-selected-tags">
          {activeDefinitions.length === 0 ? (
            <p>暂无标签</p>
          ) : activeDefinitions.map((tag) => (
            <div className="settings-selected-tag-row" key={tag.code}>
              <Chip color={tag.issueLabel ? "danger" : "default"} size="sm" variant="soft">
                <Chip.Label>{tag.label}</Chip.Label>
              </Chip>
              <span className={`settings-selected-tag-path ${tag.issueLabel ? "settings-selected-tag-path--error" : ""}`}>
                {tag.issueLabel ?? tag.path.join(" / ")}
              </span>
              <Button
                aria-label={`${tag.label} 移除`}
                isDisabled={controlsDisabled}
                isIconOnly
                size="sm"
                variant="tertiary"
                onPress={() => onRemoveTag(tag.code)}
              >
                <X aria-hidden="true" size={16} />
              </Button>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
