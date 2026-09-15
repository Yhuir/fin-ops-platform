import type { ReactNode } from "react";

import AppDrawer from "../common/AppDrawer";

type PendingInvoiceDrawerFrameProps = {
  open: boolean;
  title: string;
  closeLabel: string;
  width?: number | string;
  children: ReactNode;
  completion?: ReactNode;
  closeDisabled?: boolean;
  footer?: ReactNode;
  onClose: () => void;
};

export default function PendingInvoiceDrawerFrame({
  open,
  title,
  closeLabel,
  width = 720,
  children,
  completion,
  closeDisabled,
  footer,
  onClose,
}: PendingInvoiceDrawerFrameProps) {
  return (
    <AppDrawer
      completion={completion}
      closeDisabled={closeDisabled}
      className="pending-invoice-drawer"
      closeLabel={closeLabel}
      footer={footer}
      onClose={onClose}
      open={open}
      title={title}
      width={width}
    >
      <div className="pending-invoice-drawer__body">{children}</div>
    </AppDrawer>
  );
}
