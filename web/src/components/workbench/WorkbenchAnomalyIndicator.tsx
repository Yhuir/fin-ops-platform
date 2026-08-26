import {
  Button,
  Chip,
  Link,
  PopoverContent,
  PopoverDialog,
} from "@heroui/react";
import { CircleAlert, ExternalLink } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import {
  isWorkbenchAmountAnomalyCode,
  type WorkbenchAnomalyItem,
} from "../../features/workbench/types";
import { formatDateTimeText } from "../../features/dateTime";

type WorkbenchAnomalyIndicatorProps = {
  anomalies: WorkbenchAnomalyItem[];
  levelLabel: string;
  externalUrl?: string;
  className?: string;
  action?: {
    label: string;
    disabled?: boolean;
    disabledReason?: string;
    onPress: () => void;
  };
};

const HOVER_CLOSE_DELAY_MS = 140;

type InteractionMode = "idle" | "hover-open" | "hover-dismissed" | "click-open";

export default function WorkbenchAnomalyIndicator({
  anomalies,
  levelLabel,
  externalUrl,
  className = "",
  action,
}: WorkbenchAnomalyIndicatorProps) {
  const [interactionMode, setInteractionMode] = useState<InteractionMode>("idle");
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pointerActivationRef = useRef(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverId = useId();
  const open = interactionMode === "hover-open" || interactionMode === "click-open";

  const cancelClose = () => {
    if (closeTimerRef.current !== null) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  };
  const scheduleClose = () => {
    cancelClose();
    closeTimerRef.current = setTimeout(() => {
      closeTimerRef.current = null;
      setInteractionMode((current) => current === "hover-open" ? "idle" : current);
    }, HOVER_CLOSE_DELAY_MS);
  };

  const handleOpenChange = (nextOpen: boolean) => {
    cancelClose();
    setInteractionMode(nextOpen ? "click-open" : "idle");
  };

  const toggleFromTrigger = () => {
    cancelClose();
    setInteractionMode((current) => {
      if (current === "hover-open" || current === "click-open") {
        return "hover-dismissed";
      }
      return "click-open";
    });
  };

  useEffect(() => () => {
    if (closeTimerRef.current !== null) {
      clearTimeout(closeTimerRef.current);
    }
  }, []);

  if (anomalies.length === 0) {
    return null;
  }

  const review = anomalies.find((anomaly) => anomaly.reviewDecision === "accept_paired");
  const reviewerLabel = review
    ? `${review.reviewedByAccount}${review.reviewedByName ? `（${review.reviewedByName}）` : ""}`
    : "";
  const ariaLabel = `${levelLabel}有 ${anomalies.length} 项异常，查看详情`;

  return (
    <>
      <Button
        ref={triggerRef}
        aria-label={ariaLabel}
        aria-controls={open ? popoverId : undefined}
        aria-expanded={open}
        aria-haspopup="dialog"
        className={`workbench-anomaly-indicator__trigger${className ? ` ${className}` : ""}`}
        data-open={open ? "true" : "false"}
        isIconOnly
        size="sm"
        variant="ghost"
        onFocus={() => {
          if (pointerActivationRef.current) {
            return;
          }
          cancelClose();
          setInteractionMode((current) => current === "idle" ? "hover-open" : current);
        }}
        onHoverStart={() => {
          cancelClose();
          setInteractionMode((current) => current === "idle" ? "hover-open" : current);
        }}
        onHoverEnd={() => {
          if (interactionMode === "hover-dismissed") {
            setInteractionMode("idle");
          } else if (interactionMode === "hover-open") {
            scheduleClose();
          }
        }}
        onPointerCancel={() => {
          pointerActivationRef.current = false;
        }}
        onPointerDown={() => {
          pointerActivationRef.current = true;
        }}
        onPress={toggleFromTrigger}
        onPressEnd={() => {
          pointerActivationRef.current = false;
        }}
      >
        <CircleAlert aria-hidden="true" size={16} strokeWidth={2.1} />
      </Button>
      {open ? (
        <PopoverContent
          className="workbench-anomaly-popover"
          containerPadding={12}
          isOpen={open}
          isNonModal
          offset={6}
          placement="bottom end"
          shouldCloseOnInteractOutside={(element) => !triggerRef.current?.contains(element)}
          triggerRef={triggerRef}
          onOpenChange={handleOpenChange}
          onMouseEnter={cancelClose}
          onMouseLeave={scheduleClose}
          onPointerDown={(event) => event.stopPropagation()}
        >
          <PopoverDialog
            id={popoverId}
            aria-label={`${levelLabel}异常详情`}
            className="workbench-anomaly-popover__dialog"
          >
            <div className="workbench-anomaly-popover__heading">
              <span>{levelLabel}异常</span>
              <span>{anomalies.length} 项</span>
            </div>
            <ul className="workbench-anomaly-popover__list">
              {anomalies.map((anomaly) => {
                const detail = anomalyDetail(anomaly);
                return (
                  <li key={anomaly.fingerprint}>
                    <Chip
                      color={isWorkbenchAmountAnomalyCode(anomaly.code) ? "danger" : "warning"}
                      size="sm"
                      variant="soft"
                    >
                      <Chip.Label>{anomaly.displayLabel}</Chip.Label>
                    </Chip>
                    {detail ? <span>{detail}</span> : null}
                  </li>
                );
              })}
            </ul>
            {review ? (
              <div className="workbench-anomaly-popover__review">
                <strong>已接受该异常风险</strong>
                <dl>
                  <div>
                    <dt>操作账户</dt>
                    <dd>{reviewerLabel}</dd>
                  </div>
                  <div>
                    <dt>操作时间</dt>
                    <dd>{formatDateTimeText(review.reviewedAt)}</dd>
                  </div>
                  {review.reviewNote ? (
                    <div>
                      <dt>备注</dt>
                      <dd>{review.reviewNote}</dd>
                    </div>
                  ) : null}
                </dl>
              </div>
            ) : null}
            {action ? (
              <div className="workbench-anomaly-popover__action">
                <Button
                  isDisabled={action.disabled}
                  size="sm"
                  variant="secondary"
                  onPress={() => {
                    setInteractionMode("idle");
                    action.onPress();
                  }}
                >
                  {action.label}
                </Button>
                {action.disabled && action.disabledReason ? <span>{action.disabledReason}</span> : null}
              </div>
            ) : null}
            {externalUrl ? (
              <Link
                className="workbench-anomaly-popover__link"
                href={externalUrl}
                rel="noopener noreferrer"
                target="_blank"
                onClick={(event) => event.stopPropagation()}
              >
                打开 OA
                <ExternalLink aria-hidden="true" size={13} />
              </Link>
            ) : null}
          </PopoverDialog>
        </PopoverContent>
      ) : null}
    </>
  );
}

function anomalyDetail(anomaly: WorkbenchAnomalyItem) {
  if (anomaly.code === "oa_invoice_attachment_absent") {
    return "未发现可用发票附件";
  }
  if (anomaly.code === "oa_invoice_attachment_unparsed") {
    return `已有 ${anomaly.attachmentFileCount} 个附件，尚未解析出正式发票`;
  }
  if (anomaly.code === "oa_invoice_attachment_unassigned") {
    return "已解析发票尚未明确归属到付款项";
  }
  const totals = [
    anomaly.oaTotal ? `OA ${anomaly.oaTotal}` : "",
    anomaly.bankTotal ? `流水 ${anomaly.bankTotal}` : "",
    anomaly.invoiceTotal ? `发票 ${anomaly.invoiceTotal}` : "",
  ].filter(Boolean);
  return totals.join(" · ");
}
