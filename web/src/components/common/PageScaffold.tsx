import type { ReactNode } from "react";

type PageScaffoldProps = {
  title: string;
  titleAccessory?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
};

export default function PageScaffold({ title, titleAccessory, description, actions, children, className }: PageScaffoldProps) {
  return (
    <div className={className ? `page-stack ${className}` : "page-stack"}>
      <header className="page-header">
        <div>
          <div className="page-title-row">
            <h1 className="page-title">{title}</h1>
            {titleAccessory ? <div className="page-title-accessory">{titleAccessory}</div> : null}
          </div>
          {description ? <div className="page-description">{description}</div> : null}
        </div>
        {actions ? <div className="page-header-actions">{actions}</div> : null}
      </header>
      {children}
    </div>
  );
}
