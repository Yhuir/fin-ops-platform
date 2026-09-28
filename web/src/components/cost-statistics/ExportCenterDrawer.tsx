import SegmentedControl from "../common/SegmentedControl";
import { Button, Checkbox, Input, Radio, RadioGroup } from "@heroui/react";

import AppDrawer from "../common/AppDrawer";
import BusinessPeriodPicker, { nearbyBusinessYears } from "../common/BusinessPeriodPicker";
import type { CostStatisticsExportSummary } from "../../features/cost-statistics/types";

export type ExportCenterMode = "time" | "bank_tag" | "bank_account" | "project" | "cost_tag";
export type ExportRangeMode = "all" | "month" | "custom";

type ExportCenterDrawerProps = {
  mode: ExportCenterMode;
  projectOptions: string[];
  costTagOptions: string[];
  costTagLabels: Record<string, string>;
  bankAccountOptions: string[];
  bankAccountRangeMode: ExportRangeMode;
  bankAccountMonth: string;
  bankAccountStartDate: string;
  bankAccountEndDate: string;
  bankAccountSelections: string[];
  bankAccountProjectNames: string[];
  projectNames: string[];
  projectAggregateBy: "month" | "year";
  projectCostTags: string[];
  costTagRangeMode: ExportRangeMode;
  costTagMonth: string;
  costTagStartDate: string;
  costTagEndDate: string;
  costTagSelections: string[];
  bankFlowRangeMode: ExportRangeMode;
  bankFlowMonth: string;
  bankFlowStartDate: string;
  bankFlowEndDate: string;
  summaryData: CostStatisticsExportSummary | null;
  feedback: { tone: "success" | "error"; message: string } | null;
  isSummaryLoading: boolean;
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
  onProjectCostTagsChange: (costTags: string[]) => void;
  onCostTagRangeModeChange: (mode: ExportRangeMode) => void;
  onCostTagMonthChange: (month: string) => void;
  onCostTagStartDateChange: (date: string) => void;
  onCostTagEndDateChange: (date: string) => void;
  onCostTagSelectionsChange: (costTags: string[]) => void;
  onBankFlowRangeModeChange: (mode: ExportRangeMode) => void;
  onBankFlowMonthChange: (month: string) => void;
  onBankFlowStartDateChange: (date: string) => void;
  onBankFlowEndDateChange: (date: string) => void;
  onExport: () => void;
};

function toggleSelection(items: string[], value: string) {
  return items.includes(value) ? items.filter((item) => item !== value) : [...items, value];
}

type CostTagSelectorProps = {
  title: string;
  options: string[];
  labels?: Record<string, string>;
  selected: string[];
  onChange: (next: string[]) => void;
};

function CostTagSelector({ title, options, labels, selected, onChange }: CostTagSelectorProps) {
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
              <span>{labels ? labels[option] : option}</span>
            </Checkbox>
          ))}
        </div>
      ) : (
        <div className="cost-explorer-empty">当前没有可选成本主标签。</div>
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

export default function ExportCenterDrawer({
  mode,
  projectOptions,
  costTagOptions,
  costTagLabels,
  bankAccountOptions,
  bankAccountRangeMode,
  bankAccountMonth,
  bankAccountStartDate,
  bankAccountEndDate,
  bankAccountSelections,
  bankAccountProjectNames,
  projectNames,
  projectAggregateBy,
  projectCostTags,
  costTagRangeMode,
  costTagMonth,
  costTagStartDate,
  costTagEndDate,
  costTagSelections,
  bankFlowRangeMode,
  bankFlowMonth,
  bankFlowStartDate,
  bankFlowEndDate,
  summaryData,
  feedback,
  isSummaryLoading,
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
  onProjectCostTagsChange,
  onCostTagRangeModeChange,
  onCostTagMonthChange,
  onCostTagStartDateChange,
  onCostTagEndDateChange,
  onCostTagSelectionsChange,
  onBankFlowRangeModeChange,
  onBankFlowMonthChange,
  onBankFlowStartDateChange,
  onBankFlowEndDateChange,
  onExport,
}: ExportCenterDrawerProps) {
  return (
    <AppDrawer
      footer={(
        <>
          {feedback ? <div className={`action-feedback ${feedback.tone}`}>{feedback.message}</div> : null}
          <strong aria-live="polite">{isSummaryLoading ? '正在统计…' : summaryData ? `导出 ${summaryData.summary.transactionCount} ${mode === 'time' || mode === 'bank_tag' ? '笔' : '条成本明细'}` : '导出 —'}</strong>
          <Button isDisabled={isBusy || !summaryData || summaryData.summary.transactionCount === 0 || feedback?.tone === "error"} isPending={isExporting} onPress={onExport} variant="primary">
            {isExporting ? "正在导出..." : "导出"}
          </Button>
        </>
      )}
      className="export-center-drawer"
      closeLabel="关闭导出中心"
      closeDisabled={isExporting}
      width="min(640px, 100vw)"
      onClose={onClose}
      open
      title="导出中心"
    >
        <div className="export-center-drawer-body">
          <SegmentedControl label="导出视图切换" value={mode} disabled={isBusy} onChange={onModeChange} options={[
            { key: "time", label: "按时间" }, { key: "bank_tag", label: "按标签" },
            { key: "bank_account", label: "按银行账户" }, { key: "project", label: "按项目" },
            { key: "cost_tag", label: "按成本主标签" },
          ]} />
          {mode === "time" || mode === "bank_tag" || mode === "project" ? (
            <div className="export-center-config-grid">
              <section className="export-center-section">
                <div className="export-center-section-header">
                  <h3>时间范围</h3>
                </div>
                <RadioGroup
                  aria-label="银行流水导出时间范围"
                  className="project-export-radio-group"
                  onChange={(value) => onBankFlowRangeModeChange(value as ExportRangeMode)}
                  value={bankFlowRangeMode}
                >
                  <Radio className="project-export-choice" value="all">
                    <Radio.Control><Radio.Indicator /></Radio.Control>
                    <span>全部</span>
                  </Radio>
                  <Radio className="project-export-choice" value="month">
                    <Radio.Control><Radio.Indicator /></Radio.Control>
                    <span>自定义月份</span>
                  </Radio>
                  <Radio className="project-export-choice" value="custom">
                    <Radio.Control><Radio.Indicator /></Radio.Control>
                    <span>自定义时间区间（精确到日）</span>
                  </Radio>
                </RadioGroup>
                {bankFlowRangeMode === "month" ? (
                  <BusinessPeriodPicker
                    allowAll={false}
                    allowedModes={["month"]}
                    ariaLabel="银行流水统计月份"
                    onChange={(selection) => onBankFlowMonthChange(selection.month)}
                    selection={{ mode: "month", year: bankFlowMonth.slice(0, 4), month: bankFlowMonth }}
                    years={nearbyBusinessYears(bankFlowMonth)}
                  />
                ) : bankFlowRangeMode === "custom" ? (
                  <DateRangeFields
                    startDate={bankFlowStartDate}
                    endDate={bankFlowEndDate}
                    onStartDateChange={onBankFlowStartDateChange}
                    onEndDateChange={onBankFlowEndDateChange}
                  />
                ) : null}
              </section>
            </div>
          ) : null}

          {mode === "bank_account" ? (
            <div className="export-center-config-grid">
              <section className="export-center-section">
                <div className="export-center-section-header">
                  <h3>时间范围</h3>
                </div>
                <RadioGroup aria-label="银行账户成本时间范围" className="project-export-radio-group" onChange={(value) => onBankAccountRangeModeChange(value as ExportRangeMode)} value={bankAccountRangeMode}>
                  <Radio className="project-export-choice" value="all">
                    <Radio.Control><Radio.Indicator /></Radio.Control>
                    <span>全部</span>
                  </Radio>
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
                ) : bankAccountRangeMode === "custom" ? (
                  <DateRangeFields
                    startDate={bankAccountStartDate}
                    endDate={bankAccountEndDate}
                    onStartDateChange={onBankAccountStartDateChange}
                    onEndDateChange={onBankAccountEndDateChange}
                  />
                ) : null}
              </section>
              <CostTagSelector
                title="银行账户"
                options={bankAccountOptions}
                selected={bankAccountSelections}
                onChange={onBankAccountSelectionsChange}
              />
              <CostTagSelector
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
                <CostTagSelector
                  title="项目选择"
                  options={projectOptions}
                  selected={projectNames}
                  onChange={onProjectNamesChange}
                />
              </section>
              <CostTagSelector
                title="成本主标签"
                options={costTagOptions}
                labels={costTagLabels}
                selected={projectCostTags}
                onChange={onProjectCostTagsChange}
              />
            </div>
          ) : null}

          {mode === "cost_tag" ? (
            <div className="export-center-config-grid">
              <section className="export-center-section">
                <div className="export-center-section-header">
                  <h3>时间范围</h3>
                </div>
                <RadioGroup aria-label="成本主标签时间范围" className="project-export-radio-group" onChange={(value) => onCostTagRangeModeChange(value as ExportRangeMode)} value={costTagRangeMode}>
                  <Radio className="project-export-choice" value="all">
                    <Radio.Control><Radio.Indicator /></Radio.Control>
                    <span>全部</span>
                  </Radio>
                  <Radio className="project-export-choice" value="month">
                    <Radio.Control><Radio.Indicator /></Radio.Control>
                    <span>自定义月份</span>
                  </Radio>
                  <Radio className="project-export-choice" value="custom">
                    <Radio.Control><Radio.Indicator /></Radio.Control>
                    <span>自定义时间区间（精确到日）</span>
                  </Radio>
                </RadioGroup>
                {costTagRangeMode === "month" ? (
                  <BusinessPeriodPicker
                    allowAll={false}
                    allowedModes={["month"]}
                    ariaLabel="统计月份"
                    onChange={(selection) => onCostTagMonthChange(selection.month)}
                    selection={{ mode: "month", year: costTagMonth.slice(0, 4), month: costTagMonth }}
                    years={nearbyBusinessYears(costTagMonth)}
                  />
                ) : costTagRangeMode === "custom" ? (
                  <DateRangeFields
                    startDate={costTagStartDate}
                    endDate={costTagEndDate}
                    onStartDateChange={onCostTagStartDateChange}
                    onEndDateChange={onCostTagEndDateChange}
                  />
                ) : null}
              </section>
              <CostTagSelector
                title="成本主标签"
                options={costTagOptions}
                labels={costTagLabels}
                selected={costTagSelections}
                onChange={onCostTagSelectionsChange}
              />
            </div>
          ) : null}

          {summaryData && mode === 'project' ? <p>项目汇总 {summaryData.summary.rowCount} 条 · 成本明细 {summaryData.summary.transactionCount} 条</p> : null}

        </div>
    </AppDrawer>
  );
}
