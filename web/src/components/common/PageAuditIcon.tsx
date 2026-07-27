import { Button, Spinner, Tooltip } from "@heroui/react";
import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import type { PageAuditPayload } from "../../features/appHealth/types";

type PageAuditIconProps = {
  ariaLabel: string;
  label: string;
  resetKey?: string;
  runAudit: (signal?: AbortSignal) => Promise<PageAuditPayload>;
  successText?: string;
  notFreshText?: string;
  formatMessage?: (payload: PageAuditPayload) => {
    tone: "success" | "warning" | "danger";
    text: string;
  };
  formatError?: (error: unknown) => string;
};

function normalizeStatus(status: string | undefined) {
  return (status ?? "").trim().toLowerCase();
}

function auditMessage(
  payload: PageAuditPayload | null,
  successText: string,
  notFreshText: string,
) {
  if (!payload) {
    return null;
  }
  const summary = payload.summary;
  const blockingSamples = summary?.blocking_issue_sample_count ?? 0;
  const issueSamples = summary?.issue_sample_count ?? 0;
  const integrityPassed = payload.audit_status?.integrity === "pass";
  const auditFresh = payload.audit_status?.freshness === "fresh";
  const queueDrained = payload.audit_status?.queue === "drained";
  const proofReady = payload.audit_contract?.proof_availability === "ready";
  const contractVersioned = Boolean(payload.audit_contract?.contract_revision);
  const snapshotConsistent =
    payload.audit_contract?.database_snapshot === true &&
    payload.audit_contract?.snapshot_consistency === "repeatable_read_read_only";
  const registeredReadModelKeys = payload.audit_contract?.registered_read_model_keys;
  const directCanonicalPage = Array.isArray(registeredReadModelKeys) && registeredReadModelKeys.length === 0;
  const pageRuntimeProofReady = Array.isArray(registeredReadModelKeys);
  if (
    payload.overall_status === "pass" &&
    integrityPassed &&
    auditFresh &&
    queueDrained &&
    proofReady &&
    contractVersioned &&
    snapshotConsistent &&
    pageRuntimeProofReady &&
    blockingSamples === 0
  ) {
    const relationProofNotApplicable =
      payload.audit_contract?.relation_proof_required === false ||
      normalizeStatus(payload.audit_contract?.relation_edge_equality).startsWith("not_applicable");
    return {
      tone: "success",
      text: relationProofNotApplicable
        ? "Audit 通过 · 此数据库快照内已登记 App 内部合同一致 · 本页面不消费配对关系 · 外部来源未证明 · Fresh"
        : successText,
    };
  }
  if (integrityPassed && blockingSamples === 0) {
    if (!proofReady || !contractVersioned) {
      return { tone: "danger", text: "Audit 证明不足 · proof contract unavailable or unversioned" };
    }
    if (!snapshotConsistent) {
      return { tone: "danger", text: "Audit 证明不足 · consistency snapshot unavailable" };
    }
    if (!queueDrained) {
      return { tone: "warning", text: `${notFreshText} · queue backlog` };
    }
    const freshness = auditFresh && pageRuntimeProofReady ? "fresh" : "not_fresh";
    return { tone: "warning", text: `${notFreshText} · freshness ${freshness}` };
  }
  const truncated = summary?.issue_samples_truncated ? "+" : "";
  return {
    tone: "danger",
    text: `Audit 未通过 · integrity issues_found · blocking samples ${blockingSamples}${truncated} · issue samples ${issueSamples}${truncated}`,
  };
}

export default function PageAuditIcon({
  ariaLabel,
  label,
  resetKey,
  runAudit,
  successText = "Audit 通过 · 此数据库快照内已登记 App 内部合同一致 · 已登记配对证明一致 · 外部来源未证明 · Fresh",
  notFreshText = "Audit 完整性通过 · 已登记 App 内部合同 · Not fresh",
  formatMessage,
  formatError,
}: PageAuditIconProps) {
  const [payload, setPayload] = useState<PageAuditPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const activeControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    activeControllerRef.current?.abort();
    activeControllerRef.current = null;
    setPayload(null);
    setError(null);
    setIsLoading(false);
    return () => activeControllerRef.current?.abort();
  }, [resetKey]);

  const handleRun = useCallback(async () => {
    if (isLoading) {
      return;
    }
    const controller = new AbortController();
    activeControllerRef.current?.abort();
    activeControllerRef.current = controller;
    setIsLoading(true);
    setError(null);
    try {
      const nextPayload = await runAudit(controller.signal);
      if (!controller.signal.aborted && activeControllerRef.current === controller) {
        setPayload(nextPayload);
      }
    } catch (caught) {
      if (!controller.signal.aborted && activeControllerRef.current === controller) {
        setError(formatError?.(caught) ?? "Audit 失败");
        setPayload(null);
      }
    } finally {
      if (activeControllerRef.current === controller) {
        activeControllerRef.current = null;
        setIsLoading(false);
      }
    }
  }, [formatError, isLoading, runAudit]);

  const message = payload && formatMessage
    ? formatMessage(payload)
    : auditMessage(payload, successText, notFreshText);

  return (
    <span className="page-audit-control">
      <Tooltip delay={250}>
        <Tooltip.Trigger>
          <Button
            aria-label={ariaLabel}
            className="page-audit-icon-button"
            isDisabled={isLoading}
            isIconOnly
            onPress={handleRun}
            size="sm"
            type="button"
            variant="tertiary"
          >
            {isLoading ? <Spinner color="current" size="sm" /> : <RefreshCw aria-hidden="true" size={15} strokeWidth={2.2} />}
          </Button>
        </Tooltip.Trigger>
        <Tooltip.Content>{`Audit ${label}`}</Tooltip.Content>
      </Tooltip>
      {message ? (
        <span className="page-audit-status" data-tone={message.tone} aria-live="polite">
          {message.text}
        </span>
      ) : null}
      {error ? (
        <span className="page-audit-status" data-tone="danger" role="alert">
          {error}
        </span>
      ) : null}
    </span>
  );
}
