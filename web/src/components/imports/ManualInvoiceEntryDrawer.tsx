import { useEffect, useState } from "react";
import AppDrawer from "../common/AppDrawer";
import { confirmImportFiles } from "../../features/imports/api";
import type { ImportSessionPayload } from "../../features/imports/types";
import ManualInvoiceBatchEditor from "./ManualInvoiceBatchEditor";

type ManualInvoiceEntryDrawerProps = {
  disabled?: boolean;
  open: boolean;
  onClose: () => void;
  onImportAccepted: (payload: ImportSessionPayload) => void;
};

export default function ManualInvoiceEntryDrawer({
  disabled = false,
  open,
  onClose,
  onImportAccepted,
}: ManualInvoiceEntryDrawerProps) {
  const [completed, setCompleted] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) setCompleted(false); }, [open]);
  return (
    <AppDrawer
      completion={completed ? "发票录入已提交" : undefined}
      closeDisabled={busy}
      className="manual-invoice-entry"
      closeLabel="关闭发票录入"
      onClose={onClose}
      open={open}
      title="发票录入"
      width="min(760px, 100vw)"
    >
      <ManualInvoiceBatchEditor
        disabled={disabled}
        submitLabel="录入发票池"
        onBusyChange={setBusy}
        onSubmit={async (preview) => {
          const payload = await confirmImportFiles(preview.importSession.session.id, preview.fileIds);
          onImportAccepted(payload);
          setCompleted(true);
        }}
      />
    </AppDrawer>
  );
}
