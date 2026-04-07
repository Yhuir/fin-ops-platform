type ForbiddenPageProps = {
  title: string;
  description: string;
  tone?: "warning" | "danger";
};

export default function ForbiddenPage({
  title,
  description,
  tone = "warning",
}: ForbiddenPageProps) {
  return (
    <div className="session-screen">
      <section className={`session-card ${tone}`}>
        <div className="session-eyebrow">OA 会话校验</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </section>
    </div>
  );
}
