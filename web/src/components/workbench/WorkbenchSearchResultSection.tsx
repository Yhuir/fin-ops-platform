import type { WorkbenchSearchResult } from "../../features/search/types";
import WorkbenchSearchResultItem from "./WorkbenchSearchResultItem";

type WorkbenchSearchResultSectionProps = {
  title: string;
  results: WorkbenchSearchResult[];
  query: string;
  onDetail: (result: WorkbenchSearchResult) => void;
  onJump: (result: WorkbenchSearchResult) => void;
};

export default function WorkbenchSearchResultSection({
  title,
  results,
  query,
  onDetail,
  onJump,
}: WorkbenchSearchResultSectionProps) {
  return (
    <section aria-label={`${title} 搜索结果`} className="workbench-search-section" role="region">
      <header className="workbench-search-section-header">
        <h3>{title}</h3>
        <span>{results.length} 条</span>
      </header>
      {results.length === 0 ? (
        <div className="workbench-search-empty">当前分组暂无匹配结果。</div>
      ) : (
        <div className="workbench-search-result-list">
          {results.map((result) => (
            <WorkbenchSearchResultItem
              key={`${result.recordType}-${result.rowId}-${result.month}`}
              query={query}
              result={result}
              onDetail={onDetail}
              onJump={onJump}
            />
          ))}
        </div>
      )}
    </section>
  );
}
