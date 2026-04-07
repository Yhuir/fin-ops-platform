import MonthPicker from "../MonthPicker";
import type {
  WorkbenchSearchResponse,
  WorkbenchSearchResult,
  WorkbenchSearchScope,
  WorkbenchSearchStatus,
} from "../../features/search/types";
import WorkbenchSearchResultSection from "./WorkbenchSearchResultSection";

type WorkbenchSearchModalProps = {
  monthValue: string;
  projectOptions: string[];
  query: string;
  scope: WorkbenchSearchScope;
  monthMode: "all" | "month";
  projectName: string;
  status: WorkbenchSearchStatus;
  results: WorkbenchSearchResponse;
  isLoading: boolean;
  error: string | null;
  hint: string | null;
  isStale: boolean;
  onClose: () => void;
  onQueryChange: (value: string) => void;
  onScopeChange: (value: WorkbenchSearchScope) => void;
  onMonthModeChange: (value: "all" | "month") => void;
  onMonthValueChange: (value: string) => void;
  onProjectNameChange: (value: string) => void;
  onStatusChange: (value: WorkbenchSearchStatus) => void;
  onSubmitSearch: () => void;
  onDetail: (result: WorkbenchSearchResult) => void;
  onJump: (result: WorkbenchSearchResult) => void;
};

export default function WorkbenchSearchModal({
  monthValue,
  projectOptions,
  query,
  scope,
  monthMode,
  projectName,
  status,
  results,
  isLoading,
  error,
  hint,
  isStale,
  onClose,
  onQueryChange,
  onScopeChange,
  onMonthModeChange,
  onMonthValueChange,
  onProjectNameChange,
  onStatusChange,
  onSubmitSearch,
  onDetail,
  onJump,
}: WorkbenchSearchModalProps) {
  return (
    <div aria-modal="true" className="detail-modal-backdrop detail-modal-backdrop-foreground" role="presentation" onClick={onClose}>
      <div
        aria-label="关联台搜索"
        className="detail-modal workbench-search-modal"
        role="dialog"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="detail-modal-header">
          <div>
            <h2>关联台搜索</h2>
            <p>统一搜索 OA、银行流水、发票，并可直接跳回关联台定位到对应记录。</p>
          </div>
          <button aria-label="关闭搜索" className="detail-close-btn" type="button" onClick={onClose}>
            关闭
          </button>
        </header>

        <div className="workbench-search-controls">
          <div className="workbench-search-query-row">
            <input
              aria-label="搜索关键词"
              className="text-input workbench-search-input"
              placeholder="搜索项目、公司、人名、发票号、流水号..."
              type="search"
              value={query}
              onChange={(event) => onQueryChange(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  onSubmitSearch();
                }
              }}
            />
            <button
              aria-label="执行搜索"
              className="primary-button workbench-search-submit-btn"
              type="button"
              onClick={onSubmitSearch}
            >
              搜索
            </button>
          </div>

          <div className="workbench-search-scope-group" role="tablist" aria-label="搜索范围">
            {([
              ["all", "全部"],
              ["oa", "OA"],
              ["bank", "流水"],
              ["invoice", "发票"],
            ] as const).map(([candidateScope, label]) => (
              <button
                key={candidateScope}
                aria-selected={scope === candidateScope}
                className={`workbench-search-scope-btn${scope === candidateScope ? " active" : ""}`}
                role="tab"
                type="button"
                onClick={() => onScopeChange(candidateScope)}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="workbench-search-filter-grid">
            <div className="field-block">
              <span>时间范围</span>
              <div className="workbench-search-time-range">
                <div className="workbench-search-time-range-modes" role="group" aria-label="搜索时间范围模式">
                  <button
                    aria-pressed={monthMode === "all"}
                    className={`workbench-search-month-mode-btn${monthMode === "all" ? " active" : ""}`}
                    type="button"
                    onClick={() => onMonthModeChange("all")}
                  >
                    全时间
                  </button>
                  <button
                    aria-pressed={monthMode === "month"}
                    className={`workbench-search-month-mode-btn${monthMode === "month" ? " active" : ""}`}
                    type="button"
                    onClick={() => onMonthModeChange("month")}
                  >
                    按月份
                  </button>
                </div>
                {monthMode === "month" ? (
                  <div className="workbench-search-month-picker-shell active">
                    <MonthPicker
                      ariaLabel="搜索月份选择"
                      caption={null}
                      value={monthValue}
                      onChange={(value) => {
                        onMonthModeChange("month");
                        onMonthValueChange(value);
                      }}
                    />
                  </div>
                ) : null}
              </div>
            </div>

            <label className="field-block">
              <span>项目筛选</span>
              <select value={projectName} onChange={(event) => onProjectNameChange(event.target.value)}>
                <option value="">全部项目</option>
                {projectOptions.map((candidateProjectName) => (
                  <option key={candidateProjectName} value={candidateProjectName}>
                    {candidateProjectName}
                  </option>
                ))}
              </select>
            </label>

            <label className="field-block">
              <span>状态筛选</span>
              <select value={status} onChange={(event) => onStatusChange(event.target.value as WorkbenchSearchStatus)}>
                <option value="all">全部状态</option>
                <option value="paired">已配对</option>
                <option value="open">未配对</option>
                <option value="ignored">已忽略</option>
                <option value="processed_exception">已处理异常</option>
              </select>
            </label>
          </div>
        </div>

        <div className="workbench-search-summary-row">
          <span className="workbench-search-summary-pill">总计 {results.summary.total}</span>
          <span className="workbench-search-summary-pill">OA {results.summary.oa}</span>
          <span className="workbench-search-summary-pill">流水 {results.summary.bank}</span>
          <span className="workbench-search-summary-pill">发票 {results.summary.invoice}</span>
        </div>

        <div className="workbench-search-results">
          {!query.trim() ? <div className="detail-state-panel">输入关键词开始搜索。</div> : null}
          {query.trim() && hint ? <div className="detail-state-panel">{hint}</div> : null}
          {query.trim() && !hint && isStale ? <div className="detail-state-panel">调整条件后，点击搜索获取结果。</div> : null}
          {query.trim() && !hint && !isStale && isLoading ? <div className="detail-state-panel">正在搜索匹配记录...</div> : null}
          {query.trim() && !hint && !isStale && error ? <div className="detail-state-panel error">{error}</div> : null}
          {query.trim() && !hint && !isStale && !isLoading && !error ? (
            <>
              {results.summary.total === 0 ? (
                <div className="detail-state-panel workbench-search-empty-state">未找到匹配记录，可调整关键词或筛选条件。</div>
              ) : null}
              <WorkbenchSearchResultSection
                query={query}
                results={results.oaResults}
                title="OA"
                onDetail={onDetail}
                onJump={onJump}
              />
              <WorkbenchSearchResultSection
                query={query}
                results={results.bankResults}
                title="银行流水"
                onDetail={onDetail}
                onJump={onJump}
              />
              <WorkbenchSearchResultSection
                query={query}
                results={results.invoiceResults}
                title="发票"
                onDetail={onDetail}
                onJump={onJump}
              />
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
