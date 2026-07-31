import {
  PopoverContent,
  PopoverDialog,
  PopoverRoot,
  PopoverTrigger,
} from "@heroui/react";
import { ChevronDown } from "lucide-react";

import { useSession } from "../../contexts/SessionContext";

type AppSidebarAccountProps = {
  showExpandedContent: boolean;
};

export default function AppSidebarAccount({ showExpandedContent }: AppSidebarAccountProps) {
  const sessionState = useSession();
  const session = sessionState.status === "authenticated" || sessionState.status === "forbidden"
    ? sessionState.session
    : null;

  if (!session) {
    const label = sessionState.status === "loading" ? "账号加载中" : "账号不可用";
    return (
      <div className="app-sidebar-account app-sidebar-account--unavailable" aria-label={label} role="status">
        <span className="app-sidebar-account-avatar" aria-hidden="true">OA</span>
        <span className="app-sidebar-account-label" aria-hidden={!showExpandedContent}>{label}</span>
      </div>
    );
  }

  const { user } = session;
  const identity = user.displayName || user.username;
  const initials = Array.from(identity.trim())[0]?.toUpperCase() || "OA";

  return (
    <PopoverRoot>
      <PopoverTrigger
        aria-label={`当前账号：${identity}`}
        className="app-sidebar-account-trigger"
        title={showExpandedContent ? undefined : identity}
      >
        <span className="app-sidebar-account-avatar" aria-hidden="true">{initials}</span>
        <span className="app-sidebar-account-copy" aria-hidden={!showExpandedContent}>
          <strong>{identity}</strong>
          <span>{user.username}</span>
        </span>
        <ChevronDown aria-hidden="true" className="app-sidebar-account-chevron" size={15} strokeWidth={2.2} />
      </PopoverTrigger>
      <PopoverContent className="app-sidebar-account-popover" placement="right bottom">
        <PopoverDialog aria-label="当前 OA 账号详情" className="app-sidebar-account-dialog">
          <div className="app-sidebar-account-popover-heading">
            <span className="app-sidebar-account-avatar" aria-hidden="true">{initials}</span>
            <div>
              <strong>{identity}</strong>
              <span>当前登录 OA 账号</span>
            </div>
          </div>
          <dl className="app-sidebar-account-details">
            <div>
              <dt>账号</dt>
              <dd>{user.username}</dd>
            </div>
            {user.deptName ? (
              <div>
                <dt>部门</dt>
                <dd>{user.deptName}</dd>
              </div>
            ) : null}
          </dl>
        </PopoverDialog>
      </PopoverContent>
    </PopoverRoot>
  );
}
