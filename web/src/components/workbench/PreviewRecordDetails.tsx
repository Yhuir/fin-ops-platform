import { Button, PopoverContent, PopoverDialog } from "@heroui/react";
import { Info } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

export default function PreviewRecordDetails({
  label,
  fields,
}: {
  label: string;
  fields: [string, string][];
}) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const openedFromTriggerFocusRef = useRef(false);
  const dismissedFocusRef = useRef(false);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const id = useId();
  const cancelClose = () => {
    if (closeTimerRef.current !== null) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  };
  const close = () => {
    dismissedFocusRef.current = openedFromTriggerFocusRef.current;
    setOpen(false);
  };
  const scheduleClose = () => {
    cancelClose();
    closeTimerRef.current = setTimeout(() => {
      closeTimerRef.current = null;
      close();
    }, 140);
  };
  useEffect(() => () => {
    if (closeTimerRef.current !== null) clearTimeout(closeTimerRef.current);
  }, []);

  const visibleFields = fields.filter(
    ([, value]) => value && value !== "—" && value !== "--",
  );
  if (!visibleFields.length) return null;

  return (
    <>
      <Button
        ref={triggerRef}
        aria-label={`查看${label}`}
        aria-controls={open ? id : undefined}
        aria-expanded={open}
        aria-haspopup="dialog"
        className="relation-preview-detail-trigger"
        isIconOnly
        size="sm"
        variant="ghost"
        onHoverStart={() => {
          cancelClose();
          dismissedFocusRef.current = false;
          openedFromTriggerFocusRef.current = document.activeElement === triggerRef.current;
          setOpen(true);
        }}
        onHoverEnd={() => {
          if (dismissedFocusRef.current) dismissedFocusRef.current = false;
          else scheduleClose();
        }}
        onFocus={() => {
          // Escape restores focus to the trigger; only a new focus visit reopens it.
          if (dismissedFocusRef.current) return;
          cancelClose();
          openedFromTriggerFocusRef.current = true;
          setOpen(true);
        }}
        onBlur={() => { dismissedFocusRef.current = false; }}
        onPress={() => {
          cancelClose();
          dismissedFocusRef.current = false;
          openedFromTriggerFocusRef.current = true;
          setOpen(true);
        }}
      >
        <Info aria-hidden="true" size={16} />
      </Button>
      {open ? (
        <PopoverContent
          className="relation-preview-detail-popover"
          containerPadding={12}
          isOpen
          isNonModal
          offset={6}
          placement="bottom end"
          triggerRef={triggerRef}
          shouldCloseOnInteractOutside={(element) => !triggerRef.current?.contains(element)}
          onOpenChange={(nextOpen) => {
            cancelClose();
            if (nextOpen) setOpen(true);
            else close();
          }}
          onMouseEnter={cancelClose}
          onMouseLeave={scheduleClose}
        >
          <PopoverDialog id={id} aria-label={label} className="relation-preview-detail-popover__dialog">
            <dl>
              {visibleFields.map(([name, value]) => (
                <div key={name}>
                  <dt>{name}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          </PopoverDialog>
        </PopoverContent>
      ) : null}
    </>
  );
}
