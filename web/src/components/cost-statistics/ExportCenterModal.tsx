import { Button, Checkbox, Input, Radio, RadioGroup } from "@heroui/react";

import AppDialog from "../common/AppDialog";
import BusinessPeriodPicker, { nearbyBusinessYears } from "../common/BusinessPeriodPicker";
import {
  FinanceTable,
  FinanceTableBody,
  FinanceTableCell,
  FinanceTableColumn,
  FinanceTableHeader,
  FinanceTableRow,
} from "../common/FinanceTable";
import type { CostStatisticsExportPreview } from "../../features/cost-statistics/types";
import { formatCostAmount } from "../../features/cost-statistics/format";

export type ExportCenterMode = "bank_account" | "project" | "expense_type";
export type ExportRangeMode = "month" | "custom";

type ExportCenterModalProps = {
  mode: ExportCenterMode;
  projectOptions: string[];
  expenseTypeOptions: string[];
  bankAccountOptions: string[];
  bankAccountRangeMode: ExportRangeMode;
  bankAccountMonth: string;
  bankAccountStartDate: string;
  bankAccountEndDate: string;
  bankAccountSelections: string[];
  bankAccountProjectNames: string[];
  projectNames: string[];
  projectAggregateBy: "month" | "year";
  projectExpenseTypes: string[];
  expenseTypeRangeMode: ExportRangeMode;
  expenseTypeMonth: string;
  expenseTypeStartDate: string;
  expenseTypeEndDate: string;
  expenseTypeSelections: string[];
  preview: CostStatisticsExportPreview | null;
  feedback: { tone: "success" | "error"; message: string } | null;
  isPreviewLoading: boolean;
  isExporting: boolean;
  isBusy: boolean;
  onClose: () => void;
  onModeChange: (mode: ExportCenterMode) => void;
  onBankAccountRangeModeChange: (mode: ExportRangeMode) => void;
  onBankAccountMonthChange: (month: string) => void;
  onBankAccountStartDateChange: (date: string) => void;
  onBankAccountEndDateChange: (date: string) => void;
  onBankAccountSelectionsChange: (bankAccounts: string[]) => void;
  onBankAccountProjectNamesChange: (projectNames: string[]) => void;
  onProjectNamesChange: (projectNames: string[]) => void;
  onProjectAggregateByChange: (aggregateBy: "month" | "year") => void;
  onProjectExpenseTypesChange: (expenseTypes: string[]) => void;
  onExpenseTypeRangeModeChange: (mode: ExportRangeMode) => void;
  onExpenseTypeMonthChange: (month: string) => void;
  onExpenseTypeStartDateChange: (date: string) => void;
  onExpenseTypeEndDateChange: (date: string) => void;
  onExpenseTypeSelectionsChange: (expenseTypes: string[]) => void;
  onPreview: () => void;
  onExport: () => void;
};

function toggleSelection(items: string[], value: string) {
  return items.includes(value) ? items.filter((item) => item !== value) : [...items, value];
}

type ExpenseTypeSelectorProps = {
  title: string;
  options: string[];
  selected: string[];
  onChange: (next: string[]) => void;
};

function ExpenseTypeSelector({ title, options, selected, onChange }: ExpenseTypeSelectorProps) {
  const hasOptions = options.length > 0;
  const allSelected = hasOptions && selected.length === options.length;
  return (
    <section className="export-center-section">
      <div className="export-center-section-header">
        <h3>{title}</h3>
        <div className="export-center-inline-actions">
          <Button
            isDisabled={!hasOptions || allSelected}
            onPress={() => onChange(options)}
            size="sm"
            variant="secondary"
          >
            全选
          </Button>
          <Button
            isDisabled={selected.length === 0}
            onPress={() => onChange([])}
            size="sm"
            variant="secondary"
          >
            清空
          </Button>
        </div>
      </div>
      {hasOptions ? (
        <div className="export-center-checkbox-grid" role="group" aria-label={title}>
          {options.map((option) => (
            <Checkbox
              className="export-center-checkbox"
              isSelected={selected.includes(option)}
              key={option}
              onChange={() => onChange(toggleSelection(selected, option))}
            >
              <Checkbox.Control><Checkbox.Indicator /></Checkbox.Control>
              <span>{option}</span>
            </Checkbox>
          ))}
        </div>
      ) : (
        <div className="cost-explorer-empty">当前没有可选费用类型。</div>
      )}
    </section>
  );
}

type DateRangeFieldsProps = {
  startDate: string;
  endDate: string;
  onStartDateChange: (date: string) => void;
  onEndDateChange: (date: string) => void;
};

function DateRangeFields({ startDate, endDate, onStartDateChange, onEndDateChange }: DateRangeFieldsProps) {
  return (
    <div className="project-export-range-pickers">
      <label className="project-export-select-field">
        <span>开始日期</span>
        <Input aria-label="开始日期" type="date" value={startDate} onChange={(event) => onStartDateChange(event.currentTarget.value)} />
      </label>
      <label className="project-export-select-field">
        <span>结束日期</span>
        <Input aria-label="结束日期" type="date" value={endDate} onChange={(event) => onEndDateChange(event.currentTarget.value)} />
      </label>
    </div>
  );
}

export default function ExportCenterModal({
  mode,
  projectOptions,
  expenseTypeOptions,
  bankAccountOptions,
  bankAccountRangeMode,
  bankAccountMonth,
  bankAccountStartDate,
  bankAccountEndDate,
  bankAccountSelections,
  bankAccountProjectNames,
  projectNames,
  projectAggregateBy,
  projectExpenseTypes,
  expenseTypeRangeMode,
  expenseTypeMonth,
  expenseTypeStartDate,
  expenseTypeEndDate,
  expenseTypeSelections,
  preview,
  feedback,
  isPreviewLoading,
  isExporting,
  isBusy,
  onClose,
  onModeChange,
  onBankAccountRangeModeChange,
  onBankAccountMonthChange,
  onBankAccountStartDateChange,
  onBankAccountEndDateChange,
  onBankAccountSelectionsChange,
  onBankAccountProjectNamesChange,
  onProjectNamesChange,
  onProjectAggregateByChange,
  onProjectExpenseTypesChange,
  onExpenseTypeRangeModeChange,
  onExpenseTypeMonthChange,
  onExpenseTypeStartDateChange,
  onExpenseTypeEndDateChange,
  onExpenseTypeSelectionsChange,
  onPreview,
  onExport,
}: ExportCenterModalProps) {
  return (
    <AppDialog
      actions={(
        <>
          {feedback ? <div className={`action-feedback ${feedback.tone}`}>{feedback.message}</div> : null}
          <Button isDisabled={isBusy} onPress={onPreview} variant="secondary">
            仅预览
          </Button>
          <Button isDisabled={isBusy} isPending={isExporting} onPress={onExport} variant="primary">
            {isExporting ? "正在导出..." : "导出"}
          </Button>
        </>
      )}
      className="export-center-modal"
      closeLabel="关闭导出中心"
      disableEscapeClose={isBusy}
      isDismissable={!isBusy}
      maxWidth="lg"
      onClose={onClose}
      open
      title="导出中心"
    >
        <div className="export-center-modal-body">
          <div className="export-center-view-switcher" role="tablist" aria-label="导出视图切换">
            <Button
              aria-pressed={mode === "bank_account"}
              className="cost-view-tab"
              onPress={() => onModeChange("bank_account")}
              size="sm"
              variant={mode === "bank_account" ? "primary" : "secondary"}
            >
              按银行账户
            </Button>
            <Button
              aria-pressed={mode === "project"}
              className="cost-view-tab"
              onPress={() => onModeChange("project")}
              size="sm"
              variant={mode === "project" ? "primary" : "secondary"}
            >
              按项目
            </Button>
            <Button
              aria-pressed={mode === "expense_type"}
              className="cost-view-tab"
              onPress={() => onModeChange("expense_type")}
              size="sm"
              variant={mode === "expense_type" ? "primary" : "secondary"}
            >
              按费用类型
            </Button>
          </div>

          {mode === "bank_account" ? (
            <div className="export-center-config-grid">
              <section className="export-center-section">
                <div className="export-center-section-header">
                  <h3>时间范围</h3>
                </div>
                <RadioGroup aria-label="银行账户成本时间范围" className="project-export-radio-group" onChange={(value) => onBankAccountRangeModeChange(value as ExportRangeMode)} value={bankAccountRangeMode}>
                  <Radio className="project-export-choice" value="month">
                    <Radio.Control><Radio.Indicator /></Radio.Control>
                    <span>自定义月份</span>
                  </Radio>
                  <Radio className="project-export-choice" value="custom">
                    <Radio.Control><Radio.Indicator /></Radio.Control>
                    <span>自定义时间区间（精确到日）</span>
                  </Radio>
                </RadioGroup>
                {bankAccountRangeMode === "month" ? (
                  <BusinessPeriodPicker
                    allowAll={false}
                    allowedModes={["month"]}
                    ariaLabel="统计月份"
                    onChange={(selection) => onBankAccountMonthChange(selection.month)}
                    selection={{ mode: "month", year: bankAccountMonth.slice(0, 4), month: bankAccountMonth }}
                    years={nearbyBusinessYears(bankAccountMonth)}
                  />
                ) : (
                  <DateRangeFields
                    startDate={bankAccountStartDate}
                    endDate={bankAccountEndDate}
                    onStartDateChange={onBankAccountStartDateChange}
                    onEndDateChange={onBankAccountEndDateChange}
                  />
                )}
              </section>
              <ExpenseTypeSelector
                title="银行账户"
                options={bankAccountOptions}
                selected={bankAccountSelections}
                onChange={onBankAccountSelectionsChange}
              />
              <ExpenseTypeSelector
                title="项目（可选）"
                options={projectOptions}
                selected={bankAccountProjectNames}
                onChange={onBankAccountProjectNamesChange}
              />
            </div>
          ) : null}

          {mode === "project" ? (
            <div className="export-center-config-grid">
              <section className="export-center-section">
                <div className="export-center-section-header">
                  <h3>项目</h3>
                </div>
                <RadioGroup aria-label="项目聚合方式" className="project-export-radio-group" onChange={(value) => onProjectAggregateByChange(value as "month" | "year")} value={projectAggregateBy}>
                  <Radio className="project-export-choice" value="month">
                    <Radio.Control><Radio.Indicator /></Radio.Control>
                    <span>按月算</span>
                  </Radio>
                  <Radio className="project-export-choice" value="year">
                    <Radio.Control><Radio.Indicator /></Radio.Control>
                    <span>按年算</span>
                  </Radio>
                </RadioGroup>
                <ExpenseTypeSelector
                  title="项目选择"
                  options={projectOptions}
                  selected={projectNames}
                  onChange={onProjectNamesChange}
                />
              </section>
              <ExpenseTypeSelector
                title="费用类型"
                options={expenseTypeOptions}
                selected={projectExpenseTypes}
                onChange={onProjectExpenseTypesChange}
              />
            </div>
          ) : null}

          {mode === "expense_type" ? (
            <div className="export-center-config-grid">
              <section className="export-center-section">
                <div className="export-center-section-header">
                  <h3>时间范围</h3>
                </div>
                <RadioGroup aria-label="费用类型时间范围" className="project-export-radio-group" onChange={(value) => onExpenseTypeRangeModeChange(value as ExportRangeMode)} value={expenseTypeRangeMode}>
                  <Radio className="project-export-choice" value="month">
                    <Radio.Control><Radio.Indicator /></Radio.Control>
                    <span>自定义月份</span>
                  </Radio>
                  <Radio className="project-export-choice" value="custom">
                    <Radio.Control><Radio.Indicator /></Radio.Control>
                    <span>自定义时间区间（精确到日）</span>
                  </Radio>
                </RadioGroup>
                {expenseTypeRangeMode === "month" ? (
                  <BusinessPeriodPicker
                    allowAll={false}
                    allowedModes={["month"]}
                    ariaLabel="统计月份"
                    onChange={(selection) => onExpenseTypeMonthChange(selection.month)}
                    selection={{ mode: "month", year: expenseTypeMonth.slice(0, 4), month: expenseTypeMonth }}
                    years={nearbyBusinessYears(expenseTypeMonth)}
                  />
                ) : (
                  <DateRangeFields
                    startDate={expenseTypeStartDate}
                    endDate={expenseTypeEndDate}
                    onStartDateChange={onExpenseTypeStartDateChange}
                    onEndDateChange={onExpenseTypeEndDateChange}
                  />
                )}
              </section>
              <ExpenseTypeSelector
                title="费用类型"
                options={expenseTypeOptions}
                selected={expenseTypeSelections}
                onChange={onExpenseTypeSelectionsChange}
              />
            </div>
          ) : null}

          <section className="export-center-preview">
            <div className="export-center-preview-header">
              <h3>预览结果</h3>
              {preview ? <span>{preview.scopeLabel}</span> : null}
            </div>
            {isPreviewLoading ? (
              <div className="cost-explorer-empty">正在生成导出预览...</div>
            ) : preview ? (
              <div className="export-center-preview-body">
                <div className="export-center-preview-summary">
                  <strong>预计导出 {preview.summary.transactionCount} 条成本明细</strong>
                  <span>预计 {preview.summary.sheetCount} 个 sheet</span>
                  <span>总金额 {formatCostAmount(preview.summary.totalAmount)}</span>
                </div>
                <div className="export-center-sheet-list">
                  {preview.sheetNames.map((sheetName) => (
                    <span key={sheetName} className="export-center-sheet-chip">
                      {sheetName}
                    </span>
                  ))}
                </div>
                <div className="export-center-file-name">{preview.fileName}</div>
                <div className="cost-table-shell">
                  <FinanceTable ariaLabel="导出预览表" className="cost-table" minWidth={720}>
                    <FinanceTableHeader>
                      {preview.columns.map((column, index) => (
                        <FinanceTableColumn id={column} isRowHeader={index === 0} key={column} columnRole={column.includes("金额") ? "amount" : index === 0 ? "identity" : "description"}>{column}</FinanceTableColumn>
                      ))}
                    </FinanceTableHeader>
                    <FinanceTableBody>
                      {preview.rows.length === 0 ? (
                        <FinanceTableRow id="empty">
                          {preview.columns.map((column, index) => <FinanceTableCell className={index === 0 ? "cost-table-empty" : undefined} columnRole={column.includes("金额") ? "amount" : index === 0 ? "identity" : "description"} key={column}>{index === 0 ? "当前条件下没有可导出的成本数据。" : "-"}</FinanceTableCell>)}
                        </FinanceTableRow>
                      ) : (
                        preview.rows.map((row, rowIndex) => (
                          <FinanceTableRow id={`${rowIndex}-${row.join("-")}`} key={`${rowIndex}-${row.join("-")}`} className="cost-table-row">
                            {row.map((cell, cellIndex) => (
                              <FinanceTableCell columnRole={preview.columns[cellIndex]?.includes("金额") ? "amount" : cellIndex === 0 ? "identity" : "description"} key={`${rowIndex}-${cellIndex}`}>
                                {preview.columns[cellIndex]?.includes("金额") ? formatCostAmount(cell) : cell}
                              </FinanceTableCell>
                            ))}
                          </FinanceTableRow>
                        ))
                      )}
                    </FinanceTableBody>
                  </FinanceTable>
                </div>
              </div>
            ) : (
              <div className="cost-explorer-empty">先选择筛选条件，再点“仅预览”查看导出范围。</div>
            )}
          </section>
        </div>
    </AppDialog>
  );
}
