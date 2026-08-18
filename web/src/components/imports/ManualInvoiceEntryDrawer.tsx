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
  return (
    <AppDrawer
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
        onCancel={onClose}
        onSubmit={async (preview) => {
          const payload = await confirmImportFiles(preview.importSession.session.id, preview.fileIds);
          onImportAccepted(payload);
          onClose();
        }}
      />
    </AppDrawer>
  );
}
