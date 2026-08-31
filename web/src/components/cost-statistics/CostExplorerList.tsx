import { Chip, ListBox } from "@heroui/react";
import type { ReactNode } from "react";
import { useMemo } from "react";

type CostExplorerListProps<Row> = {
  title: string;
  count: number;
  items: Row[];
  emptyLabel: string;
  loading?: boolean;
  getKey: (row: Row) => string;
  isActive: (row: Row) => boolean;
  onSelect: (row: Row) => void;
  getPrimaryText: (row: Row) => string;
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
  getPrimaryText,
  renderSecondary,
  renderMeta,
}: CostExplorerListProps<Row>) {
  const preparedItems = useMemo(
    () => items.map((item) => ({ item, key: getKey(item), primaryText: getPrimaryText(item) })),
    [getKey, getPrimaryText, items],
  );
  const itemByKey = useMemo(
    () => new Map(preparedItems.map((prepared) => [prepared.key, prepared.item])),
    [preparedItems],
  );
  const selectedKeys = useMemo(
    () => preparedItems.filter(({ item }) => isActive(item)).map(({ key }) => key),
    [isActive, preparedItems],
  );

  return (
    <section aria-busy={loading} className="cost-explorer-lane">
      <header className="cost-explorer-lane-header">
        <h2>{title}</h2>
        <Chip className="cost-explorer-lane-count" color="default" size="sm" variant="soft">
          <Chip.Label>{count}</Chip.Label>
        </Chip>
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
        <ListBox
          aria-label={title}
          className="cost-explorer-list"
          onSelectionChange={(keys) => {
            if (keys === "all") return;
            const [key] = Array.from(keys);
            const selectedItem = itemByKey.get(String(key));
            if (selectedItem) onSelect(selectedItem);
          }}
          selectedKeys={selectedKeys}
          selectionMode="single"
        >
          {preparedItems.map(({ item, key, primaryText }) => (
            <ListBox.Item
              aria-label={`选择${title} ${primaryText}`}
              className="cost-explorer-item"
              id={key}
              key={key}
              textValue={primaryText}
            >
              <div className="cost-explorer-item-content">
                <div className="cost-explorer-item-main">
                  <strong>{primaryText}</strong>
                  {renderSecondary ? <span>{renderSecondary(item)}</span> : null}
                </div>
                {renderMeta ? <div className="cost-explorer-item-meta">{renderMeta(item)}</div> : null}
              </div>
            </ListBox.Item>
          ))}
        </ListBox>
      )}
    </section>
  );
}
