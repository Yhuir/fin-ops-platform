import { Button, Drawer } from "@heroui/react";
import { useEffect, useId, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

type AppDrawerProps = {
  open: boolean;
  title: string;
  ariaLabel?: string;
  ariaBusy?: boolean;
  className?: string;
  children: ReactNode;
  closeDisabled?: boolean;
  closeLabel?: string;
  footer?: ReactNode;
  headerActions?: ReactNode;
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
  ariaLabel,
  ariaBusy,
  className,
  children,
  closeDisabled = false,
  closeLabel,
  footer,
  headerActions,
  modal = true,
  width = 420,
  onClose,
}: AppDrawerProps) {
  const titleId = useId();
  const [persistentMounted, setPersistentMounted] = useState(open);
  const [persistentVisible, setPersistentVisible] = useState(false);
  const [persistentClosing, setPersistentClosing] = useState(false);
  const lastOpenModalContentRef = useRef({ ariaLabel, children, footer, headerActions, title });
  const persistentCloseTimerRef = useRef<number | null>(null);
  const persistentFrameRef = useRef<number | null>(null);
  const persistentOpenerRef = useRef<HTMLElement | null>(null);
  const persistentRootRef = useRef<HTMLElement | null>(null);
  const persistentWasOpenRef = useRef(false);
  const drawerStyle: AppDrawerStyle = {
    "--finance-drawer-width": typeof width === "number" ? `${width}px` : width,
  };
  if (open) {
    lastOpenModalContentRef.current = { ariaLabel, children, footer, headerActions, title };
  }
  const modalContent = open
    ? { ariaLabel, children, footer, headerActions, title }
    : lastOpenModalContentRef.current;

  useLayoutEffect(() => {
    if (!open && !persistentMounted) {
      return;
    }
    const heading = document.getElementById(titleId);
    const dialog = heading?.closest<HTMLElement>("[role='dialog'], [role='presentation']");
    if (!dialog) {
      return;
    }
    if (ariaBusy) {
      dialog.setAttribute("aria-busy", "true");
      return;
    }
    dialog.removeAttribute("aria-busy");
  }, [ariaBusy, open, persistentMounted, titleId]);

  useEffect(() => {
    if (modal) {
      return undefined;
    }

    if (persistentCloseTimerRef.current !== null) {
      window.clearTimeout(persistentCloseTimerRef.current);
      persistentCloseTimerRef.current = null;
    }
    if (persistentFrameRef.current !== null) {
      window.cancelAnimationFrame(persistentFrameRef.current);
      persistentFrameRef.current = null;
    }

    if (open) {
      if (!persistentWasOpenRef.current) {
        persistentOpenerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      }
      persistentWasOpenRef.current = true;
      setPersistentMounted(true);
      persistentFrameRef.current = window.requestAnimationFrame(() => {
        persistentFrameRef.current = null;
        setPersistentClosing(false);
        setPersistentVisible(true);
      });
      return () => {
        if (persistentFrameRef.current !== null) {
          window.cancelAnimationFrame(persistentFrameRef.current);
          persistentFrameRef.current = null;
        }
      };
    }

    if (!persistentMounted) {
      persistentWasOpenRef.current = false;
      setPersistentVisible(false);
      setPersistentClosing(false);
      return undefined;
    }

    persistentWasOpenRef.current = false;
    const focusedElement = document.activeElement;
    const opener = persistentOpenerRef.current;
    if (focusedElement instanceof Node && persistentRootRef.current?.contains(focusedElement) && opener?.isConnected) {
      opener.focus();
    }
    setPersistentVisible(false);
    setPersistentClosing(true);
    persistentCloseTimerRef.current = window.setTimeout(() => {
      persistentCloseTimerRef.current = null;
      setPersistentMounted(false);
      setPersistentVisible(false);
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
        data-entering={persistentVisible && !persistentClosing ? true : undefined}
        data-exiting={persistentClosing ? true : undefined}
        data-placement="right"
        inert={persistentClosing ? true : undefined}
        ref={persistentRootRef}
      >
        <section
          aria-busy={ariaBusy ? "true" : undefined}
          className={`finance-drawer${className ? ` ${className}` : ""}`}
          role="presentation"
          style={drawerStyle}
        >
          <header className="finance-drawer__header">
            <h2 className="finance-drawer__title" id={titleId}>
              {title}
            </h2>
            {headerActions ? <div className="finance-drawer__header-actions">{headerActions}</div> : null}
            <Button
              aria-label={closeLabel ?? "关闭抽屉"}
              isDisabled={closeDisabled}
              isIconOnly
              onPress={onClose}
              size="sm"
              variant="tertiary"
            >
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
      className="finance-drawer__backdrop"
      isDismissable={!closeDisabled}
      isKeyboardDismissDisabled={closeDisabled}
      isOpen={open}
      onOpenChange={(isOpen) => {
        if (!isOpen && !closeDisabled) {
          onClose();
        }
      }}
    >
      <Drawer.Content className="finance-drawer__content" data-placement="right" placement="right">
        <Drawer.Dialog
          aria-label={modalContent.ariaLabel}
          aria-busy={ariaBusy ? "true" : undefined}
          aria-labelledby={modalContent.ariaLabel ? undefined : titleId}
          className={`finance-drawer${className ? ` ${className}` : ""}`}
          style={drawerStyle}
        >
          <Drawer.Header className="finance-drawer__header">
            <Drawer.Heading className="finance-drawer__title" id={titleId}>
              {modalContent.title}
            </Drawer.Heading>
            {modalContent.headerActions ? (
              <div className="finance-drawer__header-actions">{modalContent.headerActions}</div>
            ) : null}
            <Button
              aria-label={closeLabel ?? "关闭抽屉"}
              isDisabled={closeDisabled}
              isIconOnly
              onPress={onClose}
              size="sm"
              variant="tertiary"
            >
              <span aria-hidden="true">×</span>
            </Button>
          </Drawer.Header>
          <Drawer.Body className="finance-drawer__body">{modalContent.children}</Drawer.Body>
          {modalContent.footer ? <Drawer.Footer className="finance-drawer__footer">{modalContent.footer}</Drawer.Footer> : null}
        </Drawer.Dialog>
      </Drawer.Content>
    </Drawer.Backdrop>
  );
}
