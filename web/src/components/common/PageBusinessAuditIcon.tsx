import { useCallback } from "react";

import { fetchPageAudit } from "../../features/appHealth/api";
import type { PageAuditPageKey } from "../../features/appHealth/types";
import PageAuditIcon from "./PageAuditIcon";

type PageBusinessAuditIconProps = {
  ariaLabel: string;
  label: string;
  pageKey: PageAuditPageKey;
  readModelStatus?: string;
  auditContextKey?: string;
};

const BUSINESS_AUDIT_SUCCESS_TEXT = "Audit 通过 · 此数据库快照内已登记 App 内部合同一致 · 已登记配对证明一致 · 外部来源未证明 · Fresh";
const BUSINESS_AUDIT_NOT_FRESH_TEXT = "Audit 完整性通过 · 已登记 App 内部合同 · Not fresh";

export default function PageBusinessAuditIcon({
  ariaLabel,
  label,
  pageKey,
  readModelStatus,
  auditContextKey,
}: PageBusinessAuditIconProps) {
  const runAudit = useCallback((signal?: AbortSignal) => fetchPageAudit(pageKey, signal), [pageKey]);

  return (
    <PageAuditIcon
      ariaLabel={ariaLabel}
      label={label}
      readModelStatus={readModelStatus}
      resetKey={auditContextKey}
      runAudit={runAudit}
      successText={BUSINESS_AUDIT_SUCCESS_TEXT}
      notFreshText={BUSINESS_AUDIT_NOT_FRESH_TEXT}
    />
  );
}
