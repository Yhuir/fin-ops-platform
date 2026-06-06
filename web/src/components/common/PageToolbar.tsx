import type { ReactNode } from "react";

type PageToolbarProps = {
  left?: ReactNode;
  right?: ReactNode;
  children?: ReactNode;
  className?: string;
};

export default function PageToolbar({ left, right, children, className }: PageToolbarProps) {
  return (
    <div className={className ? `page-toolbar ${className}` : "page-toolbar"}>
      <div className="page-toolbar__group page-toolbar__group--left">
        {left ?? children}
      </div>
      {right ? (
        <div className="page-toolbar__group page-toolbar__group--right">
          {right}
        </div>
      ) : null}
    </div>
  );
}
