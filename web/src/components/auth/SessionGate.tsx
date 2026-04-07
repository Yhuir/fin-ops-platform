import type { ReactNode } from "react";

import { useSession } from "../../contexts/SessionContext";
import ForbiddenPage from "./ForbiddenPage";

export default function SessionGate({ children }: { children: ReactNode }) {
  const session = useSession();

  if (session.status === "loading") {
    return (
      <div className="session-screen">
        <section className="session-card loading" aria-live="polite">
          <div className="session-eyebrow">OA 会话校验</div>
          <h1>正在验证 OA 会话...</h1>
          <p>请稍候，系统正在确认当前账号是否可访问财务运营平台。</p>
        </section>
      </div>
    );
  }

  if (session.status === "forbidden") {
    return (
      <ForbiddenPage
        title="无权访问财务运营平台"
        description="当前 OA 账号未开通访问权限，请联系管理员处理。"
      />
    );
  }

  if (session.status === "expired") {
    return (
      <ForbiddenPage
        title="OA 会话已失效"
        description={session.message || "请返回 OA 系统重新登录后再进入财务运营平台。"}
        tone="danger"
      />
    );
  }

  if (session.status === "error") {
    return (
      <ForbiddenPage
        title="会话校验失败"
        description={session.message || "会话校验失败，请稍后重试。"}
        tone="danger"
      />
    );
  }

  return <>{children}</>;
}
