import { useRef, useState } from "react";
import { Button, Checkbox, Input } from "@heroui/react";
import SegmentedControl from "../common/SegmentedControl";
import AppDrawer from "../common/AppDrawer";
import BusinessPeriodPicker, { type BusinessPeriodSelection } from "../common/BusinessPeriodPicker";
import type { CostStatisticsExportSummary } from "../../features/cost-statistics/types";

export type ExportCenterMode = "time" | "bank_tag" | "bank_account" | "project" | "cost_tag";

type ExportCenterDrawerProps = {
  mode: ExportCenterMode;
  period: BusinessPeriodSelection;
  years: string[];
  onPeriodChange: (period: BusinessPeriodSelection) => void;
  projectOptions: string[];
  costTagOptions: string[];
  costTagLabels: Record<string, string>;
  bankAccountOptions: string[];
  bankAccountSelections: string[];
  bankAccountProjectNames: string[];
  projectNames: string[];
  projectCostTags: string[];
  costTagSelections: string[];
  summaryData: CostStatisticsExportSummary | null;
  feedback: { tone: "success" | "error"; message: string } | null;
  isSummaryLoading: boolean;
  isExporting: boolean;
  isBusy: boolean;
  selectionEmpty: boolean;
  onClose: () => void;
  onModeChange: (mode: ExportCenterMode) => void;
  onBankAccountSelectionsChange: (accounts: string[]) => void;
  onBankAccountProjectNamesChange: (projects: string[]) => void;
  onProjectNamesChange: (projects: string[]) => void;
  onProjectCostTagsChange: (tags: string[]) => void;
  onCostTagSelectionsChange: (tags: string[]) => void;
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
  const [search, setSearch] = useState("");
  const listRef = useRef<HTMLDivElement>(null);
  const visible = options.filter(option => (labels ? labels[option] : option).toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()));
  const hasOptions = options.length > 0;
  const allSelected = hasOptions && visible.every(option => selected.includes(option));
  return (
    <section className="export-center-section">
      <div className="export-center-section-header">
        <h3>{title} <small>已选 {selected.length} / {options.length}</small></h3>
        <div className="export-center-inline-actions">
          <Button
            isDisabled={visible.length === 0 || allSelected}
            onPress={() => onChange([...new Set([...selected, ...visible])])}
            size="sm"
            variant="secondary"
          >
            {search.trim() ? "全选搜索结果" : "全选"}
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
      {options.length > 8 ? <Input aria-label={`搜索${title}`} placeholder={`搜索${title}`} value={search} onChange={event => {
        setSearch(event.target.value);
        if (listRef.current) listRef.current.scrollTop = 0;
      }} /> : null}
      <div className="export-center-list" role="region" aria-label={`${title}列表`} tabIndex={0} ref={listRef}>
        {search && visible.length === 0 ? <span role="status">无匹配{title}</span> : null}
        {hasOptions ? (
          <div className="export-center-checkbox-grid" role="group" aria-label={title}>
            {visible.map((option) => (
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
          <div className="cost-explorer-empty">暂无可选项。</div>
        )}
      </div>
    </section>
  );
}

export default function ExportCenterDrawer(props: ExportCenterDrawerProps) {
  const { mode, summaryData, feedback, isSummaryLoading, isExporting } = props;
  return <AppDrawer open title="导出中心" className="export-center-drawer" width="min(1280px, 100vw)"
    closeLabel="关闭导出中心" closeDisabled={isExporting} onClose={props.onClose}
    footer={<>
      <div className="export-center-result">
        <strong aria-live="polite">{isSummaryLoading ? "正在统计…" : summaryData ? `导出 ${summaryData.summary.transactionCount} ${mode === "time" || mode === "bank_tag" ? "笔流水" : "条成本明细"}` : props.selectionEmpty ? `导出 0 ${mode === "time" || mode === "bank_tag" ? "笔流水" : "条成本明细"}` : "导出 —"}</strong>
        {feedback ? <span role={feedback.tone === "error" ? "alert" : "status"} className={`action-feedback ${feedback.tone}`}>{feedback.message}</span> : null}
      </div>
      <Button isDisabled={props.isBusy || !summaryData || summaryData.summary.transactionCount === 0} isPending={isExporting} onPress={props.onExport} variant="primary">{isExporting ? "正在导出…" : "导出"}</Button>
    </>}>
    <div className="export-center-drawer-body">
      <div className="export-center-toolbar">
        <div className="export-center-view-group"><span>项目成本</span>
          <SegmentedControl label="项目成本导出视角" value={mode} disabled={isExporting} onChange={props.onModeChange} options={[
            { key: "project", label: "按项目" }, { key: "cost_tag", label: "按成本标签" }, { key: "bank_account", label: "按银行账户" },
          ]} />
        </div>
        <div className="export-center-view-group"><span>银行流水</span>
          <SegmentedControl label="银行流水导出视角" value={mode} disabled={isExporting} onChange={props.onModeChange} options={[
            { key: "bank_tag", label: "按标签" }, { key: "time", label: "按时间" },
          ]} />
        </div>
        <div className="export-center-period"><span>时间范围</span>
          <BusinessPeriodPicker ariaLabel="导出年月" selection={props.period} years={props.years} onChange={props.onPeriodChange} disabled={isExporting} />
        </div>
      </div>
      <fieldset key={mode} disabled={isExporting} className="export-center-options">
        {mode === "project" ? <div className="export-center-config-grid">
          <CostTagSelector title="项目" options={props.projectOptions} selected={props.projectNames} onChange={props.onProjectNamesChange} />
          <CostTagSelector title="成本主标签" options={props.costTagOptions} labels={props.costTagLabels} selected={props.projectCostTags} onChange={props.onProjectCostTagsChange} />
        </div> : null}
        {mode === "bank_account" ? <div className="export-center-config-grid">
          <CostTagSelector title="项目（可选）" options={props.projectOptions} selected={props.bankAccountProjectNames} onChange={props.onBankAccountProjectNamesChange} />
          <CostTagSelector title="银行账户" options={props.bankAccountOptions} selected={props.bankAccountSelections} onChange={props.onBankAccountSelectionsChange} />
        </div> : null}
        {mode === "cost_tag" ? <CostTagSelector title="成本主标签" options={props.costTagOptions} labels={props.costTagLabels} selected={props.costTagSelections} onChange={props.onCostTagSelectionsChange} /> : null}
      </fieldset>
    </div>
  </AppDrawer>;
}
