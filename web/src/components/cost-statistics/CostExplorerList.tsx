import type { ReactNode } from "react";

type CostExplorerListProps<Row> = {
  title: string;
  count: number;
  items: Row[];
  emptyLabel: string;
  loading?: boolean;
  getKey: (row: Row) => string;
  isActive: (row: Row) => boolean;
  onSelect: (row: Row) => void;
  renderPrimary: (row: Row) => ReactNode;
  renderSecondary?: (row: Row) => ReactNode;
  renderMeta?: (row: Row) => ReactNode;
};

export default function CostExplorerList<Row>({
  title,
  count,
  items,
  emptyLabel,
  loading = false,
  getKey,
  isActive,
  onSelect,
  renderPrimary,
  renderSecondary,
  renderMeta,
}: CostExplorerListProps<Row>) {
  return (
    <section aria-busy={loading} className="cost-explorer-lane">
      <header className="cost-explorer-lane-header">
        <h2>{title}</h2>
        <span>{count}</span>
      </header>
      {loading ? (
        <div aria-hidden="true" className="cost-explorer-lane-skeleton">
          <span />
          <span />
          <span />
        </div>
      ) : items.length === 0 ? (
        <div className="cost-explorer-empty">{emptyLabel}</div>
      ) : (
        <div className="cost-explorer-list">
          {items.map((item) => (
            <button
              key={getKey(item)}
              className={isActive(item) ? "cost-explorer-item active" : "cost-explorer-item"}
              type="button"
              onClick={() => onSelect(item)}
            >
              <div className="cost-explorer-item-main">
                <strong>{renderPrimary(item)}</strong>
                {renderSecondary ? <span>{renderSecondary(item)}</span> : null}
              </div>
              {renderMeta ? <div className="cost-explorer-item-meta">{renderMeta(item)}</div> : null}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
