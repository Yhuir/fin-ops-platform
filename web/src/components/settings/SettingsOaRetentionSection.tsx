import { Checkbox, Input, ListBox, Select } from "@heroui/react";

import OaManualSearchImportTable from "./OaManualSearchImportTable";
import type { SettingsOaRetentionSectionProps } from "./types";
import type { WorkbenchOaImportSettings } from "../../features/workbench/types";

const attachmentInvoicePromotionOptions: Array<{
  value: WorkbenchOaImportSettings["attachmentInvoicePromotionMode"];
  label: string;
}> = [
  { value: "disabled", label: "禁用晋级" },
  { value: "link_existing_only", label: "仅关联已有发票" },
  { value: "create_missing", label: "允许创建缺失发票" },
];

export default function SettingsOaRetentionSection({
  controlsDisabled,
  cutoffDate,
  oaImport,
  onChangeCutoffDate,
  onChangeAttachmentInvoicePromotionMode,
  onToggleFormType,
  onToggleStatus,
}: SettingsOaRetentionSectionProps) {
  const formTypeOptions = oaImport.availableFormTypes.filter((option) =>
    ["支付申请", "日常报销"].includes(option.label),
  );
  const statusOptions = oaImport.availableStatuses.filter((option) =>
    ["已完成", "进行中"].includes(option.label),
  );

  return (
    <section
      aria-labelledby="settings-section-oa-retention-title"
      className="settings-section-panel settings-section-panel--fluid"
      id="settings-section-oa-retention"
      role="region"
    >
      <header className="settings-section-header">
        <h3 id="settings-section-oa-retention-title">OA导入设置</h3>
      </header>
      <div className="settings-section-body">
        <div className="settings-oa-config">
          <label className="settings-field settings-field--date">
            <span>OA导入起始日期</span>
            <Input
              aria-label="OA导入起始日期"
              disabled={controlsDisabled}
              type="date"
              value={cutoffDate}
              onChange={(event) => onChangeCutoffDate(event.currentTarget.value)}
            />
          </label>

          <fieldset className="settings-checkbox-group" disabled={controlsDisabled}>
            <legend>表单类型</legend>
            <div className="settings-checkbox-list">
              {formTypeOptions.map((option) => (
                <Checkbox
                  className="settings-checkbox-row"
                  isDisabled={controlsDisabled}
                  isSelected={oaImport.formTypes.includes(option.value)}
                  key={option.value}
                  slot={null}
                  onChange={() => onToggleFormType(option.value)}
                >
                  <Checkbox.Control><Checkbox.Indicator /></Checkbox.Control>
                  <span>{option.label}</span>
                </Checkbox>
              ))}
            </div>
          </fieldset>
          <fieldset className="settings-checkbox-group" disabled={controlsDisabled}>
            <legend>流程状态</legend>
            <div className="settings-checkbox-list">
              {statusOptions.map((option) => (
                <Checkbox
                  className="settings-checkbox-row"
                  isDisabled={controlsDisabled}
                  isSelected={oaImport.statuses.includes(option.value)}
                  key={option.value}
                  slot={null}
                  onChange={() => onToggleStatus(option.value)}
                >
                  <Checkbox.Control><Checkbox.Indicator /></Checkbox.Control>
                  <span>{option.label}</span>
                </Checkbox>
              ))}
            </div>
          </fieldset>

          <label className="settings-field settings-field--promotion">
            <span>OA附件发票晋级</span>
            <Select
              aria-label="OA附件发票晋级"
              isDisabled={controlsDisabled}
              selectedKey={oaImport.attachmentInvoicePromotionMode}
              onSelectionChange={(key) =>
                onChangeAttachmentInvoicePromotionMode(
                  String(key) as WorkbenchOaImportSettings["attachmentInvoicePromotionMode"],
                )
              }
            >
              <Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger>
              <Select.Popover>
                <ListBox>
                  {attachmentInvoicePromotionOptions.map((option) => (
                    <ListBox.Item id={option.value} key={option.value} textValue={option.label}>
                      {option.label}
                    </ListBox.Item>
                  ))}
                </ListBox>
              </Select.Popover>
            </Select>
          </label>
        </div>

        <OaManualSearchImportTable />
      </div>
    </section>
  );
}
