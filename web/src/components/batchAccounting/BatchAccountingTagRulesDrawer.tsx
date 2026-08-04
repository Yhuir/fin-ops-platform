import { Button, Checkbox, Chip, Spinner } from "@heroui/react";

import type { BatchAccountingTagRules } from "../../features/batchAccounting/types";
import AppDrawer from "../common/AppDrawer";

type Props = {
  open: boolean;
  rules: BatchAccountingTagRules | null;
  selectedCodes: Set<string>;
  loading: boolean;
  saving: boolean;
  error: string | null;
  onToggle: (code: string, selected: boolean) => void;
  onClose: () => void;
  onSave: () => void;
};

function tagLabel(tag: BatchAccountingTagRules["activeTags"][number]) {
  const primary = tag.outputPrimaryLabel || tag.path[0] || tag.label;
  const secondary = tag.outputSubLabel || tag.path[1];
  return secondary && secondary !== primary ? `${primary} / ${secondary}` : primary;
}

export default function BatchAccountingTagRulesDrawer({
  open,
  rules,
  selectedCodes,
  loading,
  saving,
  error,
  onToggle,
  onClose,
  onSave,
}: Props) {
  const tags = rules?.activeTags ?? [];
  const dirty = rules ? (
    selectedCodes.size !== rules.selectedTagCodes.length
    || rules.selectedTagCodes.some((code) => !selectedCodes.has(code))
  ) : false;
  const visibleSelectedCount = tags.filter((tag) => selectedCodes.has(tag.code)).length;

  return (
    <AppDrawer
      ariaBusy={loading || saving}
      className="batch-accounting-rules-drawer"
      closeDisabled={saving}
      footer={(
        <div className="batch-accounting-rules-drawer__footer">
          <span className="batch-accounting-rules-drawer__count" role="status">
            {rules ? `已选 ${visibleSelectedCount} / ${tags.length}` : ""}
          </span>
          <div className="batch-accounting-rules-drawer__actions">
            <Button isDisabled={saving} onPress={onClose} size="sm" variant="tertiary">
              取消
            </Button>
            <Button
              isDisabled={!rules?.canSave || loading || saving || !dirty}
              onPress={onSave}
              size="sm"
              variant="primary"
            >
              {saving ? "保存中" : "保存"}
            </Button>
          </div>
        </div>
      )}
      onClose={onClose}
      open={open}
      title="批量账务标签规则"
      width={440}
    >
      <div className="batch-accounting-rules-drawer__body">
        {loading ? (
          <div className="batch-accounting-rules-drawer__state">
            <Spinner size="sm" />
            <span>正在读取标签</span>
          </div>
        ) : null}
        {error ? <div className="batch-accounting-rules-drawer__error" role="alert">{error}</div> : null}
        {!loading && !error && rules && tags.length === 0 ? (
          <div className="batch-accounting-rules-drawer__state">暂无已分类的批量账务流水</div>
        ) : null}
        {!loading && !error && rules && tags.length > 0 ? (
          <div aria-label="批量账务流水标签选择" className="batch-accounting-rules-drawer__list" role="group">
            {tags.map((tag) => (
              <Checkbox
                className="batch-accounting-rules-drawer__item"
                isDisabled={!rules.canSave || saving}
                isSelected={selectedCodes.has(tag.code)}
                key={tag.code}
                onChange={(selected) => onToggle(tag.code, selected)}
              >
                <Checkbox.Control>
                  <Checkbox.Indicator />
                </Checkbox.Control>
                <span className="batch-accounting-rules-drawer__label">{tagLabel(tag)}</span>
                <Chip color="default" size="sm" variant="soft">
                  <Chip.Label>{tag.label}</Chip.Label>
                </Chip>
              </Checkbox>
            ))}
          </div>
        ) : null}
      </div>
    </AppDrawer>
  );
}
