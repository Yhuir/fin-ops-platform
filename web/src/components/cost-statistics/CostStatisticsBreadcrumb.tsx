type BreadcrumbItem = {
  label: string;
  onClick?: () => void;
};

type CostStatisticsBreadcrumbProps = {
  items: BreadcrumbItem[];
};

export default function CostStatisticsBreadcrumb({ items }: CostStatisticsBreadcrumbProps) {
  return (
    <nav aria-label="成本统计路径" className="cost-breadcrumb">
      {items.map((item, index) => {
        const isLast = index === items.length - 1;
        return (
          <div key={`${item.label}-${index}`} className="cost-breadcrumb-item">
            {item.onClick && !isLast ? (
              <button className="cost-breadcrumb-button" type="button" onClick={item.onClick}>
                {item.label}
              </button>
            ) : (
              <span className={`cost-breadcrumb-label${isLast ? " current" : ""}`}>{item.label}</span>
            )}
            {!isLast ? <span className="cost-breadcrumb-separator">/</span> : null}
          </div>
        );
      })}
    </nav>
  );
}
