import {
  PopoverContent,
  PopoverDialog,
  PopoverRoot,
  PopoverTrigger,
} from "@heroui/react";
import { ChevronDown } from "lucide-react";

export type PageStatisticTone = "neutral" | "expense" | "income" | "success" | "warning";

export type PageStatisticItem = {
  label: string;
  value: number | null | undefined;
  unit: string;
  tone?: PageStatisticTone;
};

type PageStatisticsPopoverProps = {
  ariaLabel: string;
  coreItems: PageStatisticItem[];
  detailItems: PageStatisticItem[];
  loading?: boolean;
};

const countFormatter = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 });

function formattedValue(value: PageStatisticItem["value"]) {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0
    ? countFormatter.format(value)
    : "—";
}

function StatisticValue({ item }: { item: PageStatisticItem }) {
  const value = formattedValue(item.value);
  return (
    <span className="page-statistics-value" data-tone={item.tone ?? "neutral"}>
      <span>{item.label}</span>
      <strong>{value}</strong>
      {value === "—" ? null : <span>{item.unit}</span>}
    </span>
  );
}

export default function PageStatisticsPopover({
  ariaLabel,
  coreItems,
  detailItems,
  loading = false,
}: PageStatisticsPopoverProps) {
  return (
    <PopoverRoot>
      <PopoverTrigger aria-label={ariaLabel} className="page-statistics-trigger">
        {loading ? (
          <span aria-label="数据统计加载中" className="page-statistics-skeleton" role="status" />
        ) : (
          <span className="page-statistics-core">
            {coreItems.map((item) => <StatisticValue item={item} key={item.label} />)}
          </span>
        )}
        <ChevronDown aria-hidden="true" className="page-statistics-chevron" size={14} strokeWidth={2.2} />
      </PopoverTrigger>
      <PopoverContent className="page-statistics-popover" placement="bottom start">
        <PopoverDialog aria-label={`${ariaLabel}详情`} className="page-statistics-dialog">
          <div className="page-statistics-detail-list">
            {detailItems.map((item) => <StatisticValue item={item} key={item.label} />)}
          </div>
        </PopoverDialog>
      </PopoverContent>
    </PopoverRoot>
  );
}
