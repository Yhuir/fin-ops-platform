import { useCallback } from "react";

import { fetchPageBusinessAudit } from "../../features/appHealth/api";
import type { PageAuditDomainKey } from "../../features/appHealth/types";
import PageAuditIcon from "./PageAuditIcon";

type PageBusinessAuditIconProps = {
  ariaLabel: string;
  label: string;
  domainKey: PageAuditDomainKey;
  readModelStatus?: string;
};

const BUSINESS_AUDIT_SUCCESS_TEXT = "Audit 成功 · 全量对账通过 · Fresh";
const BUSINESS_AUDIT_NOT_FRESH_TEXT = "Audit 成功 · 全量对账通过 · Not fresh";

export default function PageBusinessAuditIcon({
  ariaLabel,
  label,
  domainKey,
  readModelStatus,
}: PageBusinessAuditIconProps) {
  const runAudit = useCallback((signal?: AbortSignal) => fetchPageBusinessAudit(domainKey, signal), [domainKey]);

  return (
    <PageAuditIcon
      ariaLabel={ariaLabel}
      label={label}
      readModelStatus={readModelStatus}
      runAudit={runAudit}
      successText={BUSINESS_AUDIT_SUCCESS_TEXT}
      notFreshText={BUSINESS_AUDIT_NOT_FRESH_TEXT}
    />
  );
}
