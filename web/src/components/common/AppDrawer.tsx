import { Button, Drawer } from "@heroui/react";
import { useEffect, useId, useRef, useState, type CSSProperties, type ReactNode } from "react";

type AppDrawerProps = {
  open: boolean;
  title: string;
  subtitle?: ReactNode;
  className?: string;
  children: ReactNode;
  closeLabel?: string;
  footer?: ReactNode;
  modal?: boolean;
  width?: number | string;
  onClose: () => void;
};

type AppDrawerStyle = CSSProperties & {
  "--finance-drawer-width": string;
};

const persistentDrawerExitMs = 180;

export default function AppDrawer({
  open,
  title,
  subtitle,
  className,
  children,
  closeLabel,
  footer,
  modal = true,
  width = 420,
  onClose,
}: AppDrawerProps) {
  const titleId = useId();
  const [persistentMounted, setPersistentMounted] = useState(open);
  const [persistentClosing, setPersistentClosing] = useState(false);
  const persistentCloseTimerRef = useRef<number | null>(null);
  const drawerStyle: AppDrawerStyle = {
    "--finance-drawer-width": typeof width === "number" ? `${width}px` : width,
  };

  useEffect(() => {
    if (modal) {
      return undefined;
    }

    if (persistentCloseTimerRef.current !== null) {
      window.clearTimeout(persistentCloseTimerRef.current);
      persistentCloseTimerRef.current = null;
    }

    if (open) {
      setPersistentMounted(true);
      setPersistentClosing(false);
      return undefined;
    }

    if (!persistentMounted) {
      setPersistentClosing(false);
      return undefined;
    }

    setPersistentClosing(true);
    persistentCloseTimerRef.current = window.setTimeout(() => {
      persistentCloseTimerRef.current = null;
      setPersistentMounted(false);
      setPersistentClosing(false);
    }, persistentDrawerExitMs);

    return () => {
      if (persistentCloseTimerRef.current !== null) {
        window.clearTimeout(persistentCloseTimerRef.current);
        persistentCloseTimerRef.current = null;
      }
    };
  }, [modal, open, persistentMounted]);

  if (!modal) {
    if (!open && !persistentMounted) {
      return null;
    }

    return (
      <aside
        aria-hidden={persistentClosing ? true : undefined}
        className="finance-drawer__content finance-drawer__content--persistent"
        data-entering={open && !persistentClosing ? true : undefined}
        data-exiting={persistentClosing ? true : undefined}
        data-placement="right"
      >
        <section className={`finance-drawer${className ? ` ${className}` : ""}`} role="presentation" style={drawerStyle}>
          <header className="finance-drawer__header">
            <div className="finance-drawer__heading">
              <h2 className="finance-drawer__title" id={titleId}>
                {title}
              </h2>
              {subtitle ? <div className="finance-drawer__subtitle">{subtitle}</div> : null}
            </div>
            <Button aria-label={closeLabel ?? "关闭抽屉"} isIconOnly onPress={onClose} size="sm" variant="tertiary">
              <span aria-hidden="true">×</span>
            </Button>
          </header>
          <div className="finance-drawer__body">{children}</div>
          {footer ? <footer className="finance-drawer__footer">{footer}</footer> : null}
        </section>
      </aside>
    );
  }

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
