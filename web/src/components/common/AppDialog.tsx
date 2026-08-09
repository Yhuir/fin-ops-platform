import { Button, Modal } from "@heroui/react";
import { X } from "lucide-react";
import { useId, type ReactNode } from "react";

type AppDialogProps = {
  open: boolean;
  title: string;
  ariaLabel?: string;
  className?: string;
  closeLabel?: string;
  description?: ReactNode;
  children?: ReactNode;
  actions?: ReactNode;
  maxWidth?: "xs" | "sm" | "md" | "lg" | "xl";
  disableEscapeClose?: boolean;
  isDismissable?: boolean;
  onClose: () => void;
};

type AppDialogMaxWidth = NonNullable<AppDialogProps["maxWidth"]>;
type ModalSize = "xs" | "sm" | "md" | "lg" | "cover";

function sizeFromMaxWidth(maxWidth: AppDialogMaxWidth): ModalSize {
  if (maxWidth === "xl") {
    return "cover";
  }
  return maxWidth;
}

export default function AppDialog({
  open,
  title,
  ariaLabel,
  className,
  closeLabel,
  description,
  children,
  actions,
  maxWidth = "sm",
  disableEscapeClose = false,
  isDismissable = true,
  onClose,
}: AppDialogProps) {
  const titleId = useId();
  const descriptionId = useId();

  return (
    <Modal.Backdrop
      isDismissable={isDismissable}
      isKeyboardDismissDisabled={disableEscapeClose}
      isOpen={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) {
          onClose();
        }
      }}
    >
      <Modal.Container placement="center" scroll="inside" size={sizeFromMaxWidth(maxWidth)}>
        <Modal.Dialog
          aria-label={ariaLabel}
          aria-describedby={description ? descriptionId : undefined}
          aria-labelledby={ariaLabel ? undefined : titleId}
          className={["finance-dialog", className].filter(Boolean).join(" ")}
        >
          <Modal.Header className="finance-dialog__header">
            <Modal.Heading className="finance-dialog__title" id={titleId}>
              {title}
            </Modal.Heading>
            {closeLabel ? (
              <Button
                aria-label={closeLabel}
                isDisabled={!isDismissable}
                isIconOnly
                onPress={onClose}
                size="sm"
                variant="tertiary"
              >
                <X aria-hidden="true" size={16} />
              </Button>
            ) : null}
          </Modal.Header>
          <Modal.Body className="finance-dialog__body">
            {description ? (
              <div className="finance-dialog__description" id={descriptionId}>
                {description}
              </div>
            ) : null}
            {children ? <div className="finance-dialog__content">{children}</div> : null}
          </Modal.Body>
          {actions ? <Modal.Footer className="finance-dialog__footer">{actions}</Modal.Footer> : null}
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>
  );
}
