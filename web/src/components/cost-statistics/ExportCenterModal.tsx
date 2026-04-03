import MonthPicker from "../MonthPicker";
import type { CostStatisticsExportPreview } from "../../features/cost-statistics/types";

export type ExportCenterMode = "time" | "project" | "expense_type";
export type ExportRangeMode = "month" | "custom";

type ExportCenterModalProps = {
  mode: ExportCenterMode;
  projectOptions: string[];
  expenseTypeOptions: string[];
  timeRangeMode: ExportRangeMode;
  timeMonth: string;
  timeStartDate: string;
  timeEndDate: string;
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
  onTimeRangeModeChange: (mode: ExportRangeMode) => void;
  onTimeMonthChange: (month: string) => void;
  onTimeStartDateChange: (date: string) => void;
  onTimeEndDateChange: (date: string) => void;
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
          <button
            className="secondary-button compact"
            type="button"
            onClick={() => onChange(options)}
            disabled={!hasOptions || allSelected}
          >
            全选
          </button>
          <button
            className="secondary-button compact"
            type="button"
            onClick={() => onChange([])}
            disabled={selected.length === 0}
          >
            清空
          </button>
        </div>
      </div>
      {hasOptions ? (
        <div className="export-center-checkbox-grid" role="group" aria-label={title}>
          {options.map((option) => (
            <label key={option} className="export-center-checkbox">
              <input
                checked={selected.includes(option)}
                type="checkbox"
                onChange={() => onChange(toggleSelection(selected, option))}
              />
              <span>{option}</span>
            </label>
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
        <input aria-label="开始日期" type="date" value={startDate} onChange={(event) => onStartDateChange(event.currentTarget.value)} />
      </label>
      <label className="project-export-select-field">
        <span>结束日期</span>
        <input aria-label="结束日期" type="date" value={endDate} onChange={(event) => onEndDateChange(event.currentTarget.value)} />
      </label>
    </div>
  );
}

export default function ExportCenterModal({
  mode,
  projectOptions,
  expenseTypeOptions,
  timeRangeMode,
  timeMonth,
  timeStartDate,
  timeEndDate,
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
  onTimeRangeModeChange,
  onTimeMonthChange,
  onTimeStartDateChange,
  onTimeEndDateChange,
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
    <div className="export-center-modal-layer" role="presentation">
      <button aria-label="关闭导出中心" className="export-center-modal-backdrop" type="button" onClick={onClose} />
      <section aria-labelledby="export-center-modal-title" aria-modal="true" className="export-center-modal" role="dialog">
        <header className="export-center-modal-header">
          <div>
            <h2 id="export-center-modal-title">导出中心</h2>
            <p>统一配置按时间、按项目和按费用类型的成本统计导出，并在下载前先查看预览范围。</p>
          </div>
          <button className="secondary-button" type="button" onClick={onClose} disabled={isBusy}>
            关闭
          </button>
        </header>

        <div className="export-center-modal-body">
          <div className="export-center-view-switcher" role="tablist" aria-label="导出视图切换">
            <button
              className={mode === "time" ? "cost-view-tab active" : "cost-view-tab"}
              type="button"
              onClick={() => onModeChange("time")}
            >
              按时间
            </button>
            <button
              className={mode === "project" ? "cost-view-tab active" : "cost-view-tab"}
              type="button"
              onClick={() => onModeChange("project")}
            >
              按项目
            </button>
            <button
              className={mode === "expense_type" ? "cost-view-tab active" : "cost-view-tab"}
              type="button"
              onClick={() => onModeChange("expense_type")}
            >
              按费用类型
            </button>
          </div>

          {mode === "time" ? (
            <div className="export-center-config-grid">
              <section className="export-center-section">
                <div className="export-center-section-header">
                  <h3>时间范围</h3>
                </div>
                <div className="project-export-radio-group">
                  <label className="project-export-choice">
                    <input
                      checked={timeRangeMode === "month"}
                      name="time-export-range"
                      type="radio"
                      onChange={() => onTimeRangeModeChange("month")}
                    />
                    <span>自定义月份</span>
                  </label>
                  <label className="project-export-choice">
                    <input
                      checked={timeRangeMode === "custom"}
                      name="time-export-range"
                      type="radio"
                      onChange={() => onTimeRangeModeChange("custom")}
                    />
                    <span>自定义时间区间（精确到日）</span>
                  </label>
                </div>
                {timeRangeMode === "month" ? (
                  <MonthPicker ariaLabel="统计月份" caption="统计月份" value={timeMonth} onChange={onTimeMonthChange} />
                ) : (
                  <DateRangeFields
                    startDate={timeStartDate}
                    endDate={timeEndDate}
                    onStartDateChange={onTimeStartDateChange}
                    onEndDateChange={onTimeEndDateChange}
                  />
                )}
              </section>
            </div>
          ) : null}

          {mode === "project" ? (
            <div className="export-center-config-grid">
              <section className="export-center-section">
                <div className="export-center-section-header">
                  <h3>项目</h3>
                </div>
                <div className="project-export-radio-group">
                  <label className="project-export-choice">
                    <input
                      checked={projectAggregateBy === "month"}
                      name="project-export-aggregate"
                      type="radio"
                      onChange={() => onProjectAggregateByChange("month")}
                    />
                    <span>按月算</span>
                  </label>
                  <label className="project-export-choice">
                    <input
                      checked={projectAggregateBy === "year"}
                      name="project-export-aggregate"
                      type="radio"
                      onChange={() => onProjectAggregateByChange("year")}
                    />
                    <span>按年算</span>
                  </label>
                </div>
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
                <div className="project-export-radio-group">
                  <label className="project-export-choice">
                    <input
                      checked={expenseTypeRangeMode === "month"}
                      name="expense-type-export-range"
                      type="radio"
                      onChange={() => onExpenseTypeRangeModeChange("month")}
                    />
                    <span>自定义月份</span>
                  </label>
                  <label className="project-export-choice">
                    <input
                      checked={expenseTypeRangeMode === "custom"}
                      name="expense-type-export-range"
                      type="radio"
                      onChange={() => onExpenseTypeRangeModeChange("custom")}
                    />
                    <span>自定义时间区间（精确到日）</span>
                  </label>
                </div>
                {expenseTypeRangeMode === "month" ? (
                  <MonthPicker ariaLabel="统计月份" caption="统计月份" value={expenseTypeMonth} onChange={onExpenseTypeMonthChange} />
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
                  <strong>预计导出 {preview.summary.transactionCount} 条流水</strong>
                  <span>预计 {preview.summary.sheetCount} 个 sheet</span>
                  <span>总金额 {preview.summary.totalAmount}</span>
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
                  <table aria-label="导出预览表" className="cost-table">
                    <thead>
                      <tr>
                        {preview.columns.map((column) => (
                          <th key={column}>{column}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {preview.rows.length === 0 ? (
                        <tr>
                          <td className="cost-table-empty" colSpan={preview.columns.length}>
                            当前条件下没有可导出的成本数据。
                          </td>
                        </tr>
                      ) : (
                        preview.rows.map((row, rowIndex) => (
                          <tr key={`${rowIndex}-${row.join("-")}`} className="cost-table-row">
                            {row.map((cell, cellIndex) => (
                              <td key={`${rowIndex}-${cellIndex}`}>{cell}</td>
                            ))}
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <div className="cost-explorer-empty">先选择筛选条件，再点“仅预览”查看导出范围。</div>
            )}
          </section>
        </div>

        <footer className="export-center-modal-footer">
          {feedback ? <div className={`action-feedback ${feedback.tone}`}>{feedback.message}</div> : null}
          <button className="secondary-button" type="button" onClick={onPreview} disabled={isBusy}>
            仅预览
          </button>
          <button className="cost-export-button" type="button" onClick={onExport} disabled={isBusy}>
            {isExporting ? "正在导出..." : "导出"}
          </button>
        </footer>
      </section>
    </div>
  );
}
