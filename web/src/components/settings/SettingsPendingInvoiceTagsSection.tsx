import { Plus, X } from "lucide-react";
import { useState } from "react";

import type { SettingsPendingInvoiceTagsSectionProps } from "./types";

const GROUP_LABELS: Record<SettingsPendingInvoiceTagsSectionProps["activeGroup"], string> = {
  requiresInvoice: "需要开票",
  bankStatementAsInvoice: "流水代替发票",
  noInvoiceRequired: "无需开票",
};

const GROUP_DESCRIPTIONS: Record<SettingsPendingInvoiceTagsSectionProps["activeGroup"], string> = {
  requiresInvoice: "缺进项票时允许选择已有发票",
  bankStatementAsInvoice: "流水可替票，通常无需选择发票",
  noInvoiceRequired: "缺进项票时不显示发票选择入口",
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
  const [isExistingTagMenuOpen, setIsExistingTagMenuOpen] = useState(false);
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

  function addExistingTag(code: string) {
    onAddExistingTag(code);
    setSelectedTagCode("");
    setIsExistingTagMenuOpen(false);
  }

  return (
    <section
      aria-labelledby="settings-section-pending-invoice-tags-title"
      className="settings-section-panel"
      id="settings-section-pending-invoice-tags"
      role="region"
    >
      <header className="settings-section-header">
        <h3 id="settings-section-pending-invoice-tags-title">待找发票筛选</h3>
      </header>
      <div className="settings-section-body">
        <div className="settings-pending-tags-layout">
          <div className="settings-pending-group-list" aria-label="待找发票筛选分组">
            {(Object.keys(GROUP_LABELS) as Array<keyof typeof GROUP_LABELS>).map((group) => (
              <button
                key={group}
                aria-pressed={activeGroup === group}
                className="settings-pending-group-button"
                type="button"
                onClick={() => onSelectGroup(group)}
              >
                <span>
                  <strong>{GROUP_LABELS[group]}</strong>
                  <small>{GROUP_DESCRIPTIONS[group]}</small>
                </span>
                <em>{groups[group].length}</em>
              </button>
            ))}
          </div>

          <div className="settings-pending-tag-panel">
            <div className="settings-pending-tag-toolbar">
              <label className="settings-field">
                <span>已有标签</span>
                <select
                  className="settings-select-control"
                  disabled={controlsDisabled}
                  value={selectedTagCode}
                  onChange={(event) => setSelectedTagCode(event.currentTarget.value)}
                >
                  <option value="">选择标签</option>
                  {availableTags.map((tag) => (
                    <option key={tag.code} value={tag.code}>{tag.label}</option>
                  ))}
                </select>
              </label>
              <div className="settings-menu-trigger-wrap">
                <button
                  aria-expanded={isExistingTagMenuOpen}
                  aria-haspopup="menu"
                  className="settings-secondary-button"
                  disabled={controlsDisabled || availableTags.length === 0}
                  type="button"
                  onClick={() => {
                    if (selectedTagCode) {
                      addExistingTag(selectedTagCode);
                      return;
                    }
                    setIsExistingTagMenuOpen((current) => !current);
                  }}
                >
                  <Plus aria-hidden="true" size={16} />
                  选择现有标签
                </button>
                {isExistingTagMenuOpen ? (
                  <div className="settings-menu" role="menu" aria-label="可选自动标签">
                    {availableTags.map((tag) => (
                      <button
                        key={tag.code}
                        role="menuitem"
                        type="button"
                        onClick={() => addExistingTag(tag.code)}
                      >
                        {tag.label}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            </div>

            <div className="settings-selected-tags">
              {activeDefinitions.length === 0 ? (
                <p>当前分组未选择自动标签。</p>
              ) : activeDefinitions.map((tag) => (
                <div className="settings-selected-tag-row" key={tag.code}>
                  <span className={`settings-selected-tag ${tag.issueLabel ? "settings-selected-tag--error" : ""}`}>
                    {tag.label}
                  </span>
                  <span className={`settings-selected-tag-path ${tag.issueLabel ? "settings-selected-tag-path--error" : ""}`}>
                    {tag.issueLabel ?? tag.path.join(" / ")}
                  </span>
                  <button
                    aria-label={`${tag.label} 移除`}
                    className="settings-icon-button"
                    disabled={controlsDisabled}
                    title="移除标签"
                    type="button"
                    onClick={() => onRemoveTag(tag.code)}
                  >
                    <X aria-hidden="true" size={16} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
