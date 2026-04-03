import type { WorkbenchSearchResult } from "../../features/search/types";

type WorkbenchSearchResultItemProps = {
  query: string;
  result: WorkbenchSearchResult;
  onDetail: (result: WorkbenchSearchResult) => void;
  onJump: (result: WorkbenchSearchResult) => void;
};

export default function WorkbenchSearchResultItem({
  query,
  result,
  onDetail,
  onJump,
}: WorkbenchSearchResultItemProps) {
  return (
    <article className="workbench-search-result-item" data-search-result-item="true">
      <div className="workbench-search-result-main">
        <div className="workbench-search-result-title">{highlightQuery(result.title, query)}</div>
        <div className="workbench-search-result-meta">
          <span>{highlightQuery(result.primaryMeta, query)}</span>
          <span>{highlightQuery(result.secondaryMeta, query)}</span>
        </div>
      </div>
      <div className="workbench-search-result-side">
        <div className="workbench-search-result-tags">
          <span className="workbench-search-tag">{formatMonthLabel(result.month)}</span>
          <span className="workbench-search-tag">{result.statusLabel}</span>
        </div>
        <div className="workbench-search-result-actions">
          <button className="secondary-button" type="button" onClick={() => onDetail(result)}>
            详情
          </button>
          <button className="secondary-button" type="button" onClick={() => onJump(result)}>
            跳转至
          </button>
        </div>
      </div>
    </article>
  );
}

function formatMonthLabel(month: string) {
  const [yearText, monthText] = month.split("-");
  const year = Number.parseInt(yearText, 10);
  const monthValue = Number.parseInt(monthText, 10);
  if (!Number.isFinite(year) || !Number.isFinite(monthValue)) {
    return month;
  }
  return `${year}年${monthValue}月`;
}

function highlightQuery(text: string, query: string) {
  const normalizedQuery = query.trim();
  if (!normalizedQuery) {
    return text;
  }

  const safePattern = normalizedQuery.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const matcher = new RegExp(`(${safePattern})`, "ig");
  const parts = text.split(matcher);

  if (parts.length === 1) {
    return text;
  }

  return parts.map((part, index) =>
    part.toLowerCase() === normalizedQuery.toLowerCase() ? (
      <mark key={`${part}-${index}`} className="workbench-search-highlight">
        {part}
      </mark>
    ) : (
      <span key={`${part}-${index}`}>{part}</span>
    ),
  );
}
