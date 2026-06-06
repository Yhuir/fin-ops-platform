import type { ReactNode } from "react";

type PageScaffoldProps = {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
};

export default function PageScaffold({ title, description, actions, children, className }: PageScaffoldProps) {
  return (
    <div className={className ? `page-stack ${className}` : "page-stack"}>
      <header className="page-header">
        <div>
          <h1 className="page-title">{title}</h1>
          {description ? <div className="page-description">{description}</div> : null}
        </div>
        {actions ? <div className="page-header-actions">{actions}</div> : null}
      </header>
      {children}
    </div>
  );
}
