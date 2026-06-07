import { Button, Drawer } from "@heroui/react";
import { useId, type CSSProperties, type ReactNode } from "react";

type AppDrawerProps = {
  open: boolean;
  title: string;
  subtitle?: ReactNode;
  className?: string;
  children: ReactNode;
  closeLabel?: string;
  footer?: ReactNode;
  width?: number | string;
  onClose: () => void;
};

type AppDrawerStyle = CSSProperties & {
  "--finance-drawer-width": string;
};

export default function AppDrawer({
  open,
  title,
  subtitle,
  className,
  children,
  closeLabel,
  footer,
  width = 420,
  onClose,
}: AppDrawerProps) {
  const titleId = useId();
  const drawerStyle: AppDrawerStyle = {
    "--finance-drawer-width": typeof width === "number" ? `${width}px` : width,
  };

  return (
    <Drawer.Backdrop
      isOpen={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) {
          onClose();
        }
      }}
    >
      <Drawer.Content className="finance-drawer__content" data-placement="right" placement="right">
        <Drawer.Dialog aria-labelledby={titleId} className={`finance-drawer${className ? ` ${className}` : ""}`} style={drawerStyle}>
          <Drawer.Header className="finance-drawer__header">
            <div className="finance-drawer__heading">
              <Drawer.Heading className="finance-drawer__title" id={titleId}>
                {title}
              </Drawer.Heading>
              {subtitle ? <div className="finance-drawer__subtitle">{subtitle}</div> : null}
            </div>
            <Button aria-label={closeLabel ?? "关闭抽屉"} isIconOnly onPress={onClose} size="sm" variant="tertiary">
              <span aria-hidden="true">×</span>
            </Button>
          </Drawer.Header>
          <Drawer.Body className="finance-drawer__body">{children}</Drawer.Body>
          {footer ? <Drawer.Footer className="finance-drawer__footer">{footer}</Drawer.Footer> : null}
        </Drawer.Dialog>
      </Drawer.Content>
    </Drawer.Backdrop>
  );
}
