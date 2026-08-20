import { Button, Chip } from "@heroui/react";
import type { ReactNode } from "react";
import { useLayoutEffect, useMemo, useRef, useState } from "react";

function sameKeys(left: Set<string>, right: Set<string>) {
  if (left.size !== right.size) {
    return false;
  }
  for (const key of left) {
    if (!right.has(key)) {
      return false;
    }
  }
  return true;
}

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
  const listRef = useRef<HTMLDivElement | null>(null);
  const labelRefs = useRef(new Map<string, HTMLElement>());
  const [overflowedKeys, setOverflowedKeys] = useState<Set<string>>(() => new Set());
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const preparedItems = useMemo(
    () => items.map((item) => ({ item, key: getKey(item), primaryText: getPrimaryText(item) })),
    [getKey, getPrimaryText, items],
  );

  useLayoutEffect(() => {
    const list = listRef.current;
    if (!list) {
      return undefined;
    }

    let frameId: number | null = null;
    const measure = () => {
      frameId = null;
      const nextOverflowedKeys = new Set<string>();

      for (const { key } of preparedItems) {
        if (key === expandedKey) {
          nextOverflowedKeys.add(key);
          continue;
        }
        const label = labelRefs.current.get(key);
        if (!label) {
          continue;
        }
        if (label.scrollWidth > label.clientWidth + 1) {
          nextOverflowedKeys.add(key);
        }
      }

      setOverflowedKeys((current) => sameKeys(current, nextOverflowedKeys) ? current : nextOverflowedKeys);
      setExpandedKey((current) => current && !nextOverflowedKeys.has(current) ? null : current);
    };
    const scheduleMeasure = () => {
      if (frameId !== null) {
        window.cancelAnimationFrame(frameId);
      }
      frameId = window.requestAnimationFrame(measure);
    };

    measure();
    if (typeof ResizeObserver === "undefined") {
      return () => {
        if (frameId !== null) {
          window.cancelAnimationFrame(frameId);
        }
      };
    }

    const observer = new ResizeObserver(scheduleMeasure);
    observer.observe(list);
    return () => {
      observer.disconnect();
      if (frameId !== null) {
        window.cancelAnimationFrame(frameId);
      }
    };
  }, [expandedKey, preparedItems]);

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
        <div className="cost-explorer-list" ref={listRef}>
          {preparedItems.map(({ item, key, primaryText }) => {
            const active = isActive(item);
            const overflowed = overflowedKeys.has(key);
            const expanded = expandedKey === key;
            return (
              <div
                className={[
                  "cost-explorer-item",
                  active ? "active" : "",
                  expanded ? "is-expanded" : "",
                ].filter(Boolean).join(" ")}
                key={key}
              >
                <Button
                  aria-label={`选择${title} ${primaryText}`}
                  aria-pressed={active}
                  className="cost-explorer-item-select"
                  onPress={() => {
                    setExpandedKey(null);
                    onSelect(item);
                  }}
                  size="sm"
                  variant="tertiary"
                >
                  <div className="cost-explorer-item-main">
                    <strong
                      ref={(element) => {
                        if (element) {
                          labelRefs.current.set(key, element);
                        } else {
                          labelRefs.current.delete(key);
                        }
                      }}
                    >
                      {primaryText}
                    </strong>
                    {renderSecondary ? <span>{renderSecondary(item)}</span> : null}
                  </div>
                  {renderMeta ? <div className="cost-explorer-item-meta">{renderMeta(item)}</div> : null}
                </Button>
                {overflowed ? (
                  <Button
                    aria-expanded={expanded}
                    aria-label={`${expanded ? "折叠" : "展开"}${title}完整内容`}
                    className="cost-explorer-item-disclosure"
                    onPress={() => setExpandedKey((current) => current === key ? null : key)}
                    size="sm"
                    variant="tertiary"
                  >
                    {expanded ? "折叠" : "展开"}
                  </Button>
                ) : null}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
