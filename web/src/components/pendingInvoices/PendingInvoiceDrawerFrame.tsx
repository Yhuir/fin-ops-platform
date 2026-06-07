import type { ReactNode } from "react";

import AppDrawer from "../common/AppDrawer";

type PendingInvoiceDrawerFrameProps = {
  open: boolean;
  title: string;
  subtitle?: string;
  closeLabel: string;
  width?: number;
  children: ReactNode;
  footer?: ReactNode;
  contentSx?: unknown;
  onClose: () => void;
};

export default function PendingInvoiceDrawerFrame({
  open,
  title,
  subtitle,
  closeLabel,
  width = 720,
  children,
  footer,
  onClose,
}: PendingInvoiceDrawerFrameProps) {
  return (
    <AppDrawer
      className="pending-invoice-drawer"
      closeLabel={closeLabel}
      footer={footer}
      onClose={onClose}
      open={open}
      subtitle={subtitle}
      title={title}
      width={width}
    >
      <div className="pending-invoice-drawer__body">{children}</div>
    </AppDrawer>
  );
}
