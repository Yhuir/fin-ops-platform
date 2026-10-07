import { PopoverContent, PopoverDialog, PopoverRoot, PopoverTrigger } from "@heroui/react";
import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import "./compactPageHeader.css";

type PageScaffoldProps = {
  title: string;
  titleAccessory?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  query?: ReactNode;
  secondaryActions?: ReactNode;
  children: ReactNode;
  className?: string;
  fillViewport?: boolean;
};

export default function PageScaffold({ title, titleAccessory, description, actions, query, secondaryActions, children, className, fillViewport = false }: PageScaffoldProps) {
  const headerRef = useRef<HTMLElement>(null);
  const [compactActions, setCompactActions] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const hasQuery = Boolean(query);
  useLayoutEffect(() => {
    if (!hasQuery || !headerRef.current) return;
    const header = headerRef.current;
    const update = () => setCompactActions(header.clientWidth < 1500);
    const observer = new ResizeObserver(update);
    observer.observe(header);
    return () => observer.disconnect();
  }, [hasQuery]);
  return (
    <div className={["page-stack", fillViewport && "page-stack--table", hasQuery && "page-stack--query", className].filter(Boolean).join(" ")}>
      <header className="page-header" ref={headerRef}>
        <div>
          <div className="page-title-row">
            <h1 className="page-title">{title}</h1>
            {titleAccessory ? <div className="page-title-accessory">{titleAccessory}</div> : null}
          </div>
          {description ? <div className="page-description">{description}</div> : null}
        </div>
        {query ? <div className="page-header-query">{query}</div> : null}
        {actions || secondaryActions ? <div className="page-header-actions">
          {actions}
          {secondaryActions && (compactActions ? <PopoverRoot isOpen={moreOpen} onOpenChange={setMoreOpen}>
            <PopoverTrigger className="button button--sm button--secondary" aria-label="更多页面操作">更多 ▾</PopoverTrigger>
            <PopoverContent placement="bottom end" className="page-header-more-popover">
              <PopoverDialog aria-label="更多页面操作" className="page-header-more-actions" onClickCapture={() => setMoreOpen(false)}>{secondaryActions}</PopoverDialog>
            </PopoverContent>
          </PopoverRoot> : secondaryActions)}
        </div> : null}
      </header>
      {children}
    </div>
  );
}
