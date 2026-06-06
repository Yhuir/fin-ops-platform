import type { ReactNode } from "react";

type ForbiddenPageProps = {
  title: string;
  description: string;
  tone?: "warning" | "danger";
  action?: ReactNode;
};

export default function ForbiddenPage({
  title,
  description,
  tone = "warning",
  action,
}: ForbiddenPageProps) {
  return (
    <div className="session-screen">
      <section className={`session-card ${tone}`}>
        <div className="session-eyebrow">OA 会话校验</div>
        <h1>{title}</h1>
        <p>{description}</p>
        {action ? <div className="session-actions">{action}</div> : null}
      </section>
    </div>
  );
}
