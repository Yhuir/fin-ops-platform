import { Alert } from "@heroui/react";
import type { ReactNode } from "react";

type PermissionNoticeProps = {
  children: ReactNode;
};

export default function PermissionNotice({ children }: PermissionNoticeProps) {
  return (
    <Alert className="finance-state-panel finance-state-panel--warning" role="status" status="warning">
      <Alert.Indicator />
      <Alert.Content className="finance-state-panel__content">
        <div className="finance-state-panel__description">{children}</div>
      </Alert.Content>
    </Alert>
  );
}
