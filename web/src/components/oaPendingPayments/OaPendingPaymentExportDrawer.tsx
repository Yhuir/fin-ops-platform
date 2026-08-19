import { Button, Checkbox } from "@heroui/react";
import { useEffect, useState } from "react";

import type {
  OaPendingPaymentExportDownload,
  OaPendingPaymentExportSource,
} from "../../features/oaPendingPayments/api";
import AppDrawer from "../common/AppDrawer";

const allSources: OaPendingPaymentExportSource[] = ["completed", "in_progress"];

type OaPendingPaymentExportDrawerProps = {
  open: boolean;
  downloadExport: (sources: OaPendingPaymentExportSource[]) => Promise<OaPendingPaymentExportDownload>;
  onClose: () => void;
};

export default function OaPendingPaymentExportDrawer({
  open,
  downloadExport,
  onClose,
}: OaPendingPaymentExportDrawerProps) {
  const [selectedSources, setSelectedSources] = useState<Set<OaPendingPaymentExportSource>>(
    () => new Set(allSources),
  );
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [downloadedFileName, setDownloadedFileName] = useState("");

  useEffect(() => {
    if (!open) {
      setSelectedSources(new Set(allSources));
      setDownloading(false);
      setError(null);
      setDownloadedFileName("");
    }
  }, [open]);

  const allSelected = selectedSources.size === allSources.length;

  function toggleAll() {
    setSelectedSources(allSelected ? new Set() : new Set(allSources));
    setError(null);
  }

  function toggleSource(source: OaPendingPaymentExportSource) {
    setSelectedSources((current) => {
      const next = new Set(current);
      if (next.has(source)) {
        next.delete(source);
      } else {
        next.add(source);
      }
      return next;
    });
    setError(null);
  }

  async function handleDownload() {
    if (downloading || selectedSources.size === 0) {
      return;
    }
    setDownloading(true);
    setError(null);
    setDownloadedFileName("");
    try {
      const sources = allSources.filter((source) => selectedSources.has(source));
      const result = await downloadExport(sources);
      triggerDownload(result);
      setDownloadedFileName(result.fileName);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "OA 导出失败。");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <AppDrawer
      ariaBusy={downloading}
      ariaLabel="导出 OA 抽屉"
      className="oa-pending-payment-export-drawer"
      closeDisabled={downloading}
      closeLabel="关闭导出 OA 抽屉"
      footer={(
        <div className="oa-pending-payment-export-drawer__footer">
          <Button isDisabled={downloading} onPress={onClose} size="sm" variant="secondary">
            取消
          </Button>
          <Button
            className="oa-pending-payments-button oa-pending-payments-button--primary"
            isDisabled={downloading || selectedSources.size === 0}
            isPending={downloading}
            onPress={handleDownload}
            size="sm"
            variant="primary"
          >
            导出 xlsx
          </Button>
        </div>
      )}
      onClose={onClose}
      open={open}
      title="导出 OA 事实源"
      width="min(440px, 100vw)"
    >
      <div className="oa-pending-payment-export-drawer__body">
        <p>选择需要导出的 OA 来源。导出范围不受当前页面月份、搜索、筛选或分页影响。</p>
        <div className="oa-pending-payment-export-drawer__options">
          <ExportSourceCheckbox
            checked={allSelected}
            indeterminate={selectedSources.size > 0 && !allSelected}
            label="全选"
            onChange={toggleAll}
          />
          <ExportSourceCheckbox
            checked={selectedSources.has("completed")}
            label="已完成 OA"
            onChange={() => toggleSource("completed")}
          />
          <ExportSourceCheckbox
            checked={selectedSources.has("in_progress")}
            label="进行中 OA"
            onChange={() => toggleSource("in_progress")}
          />
        </div>
        {selectedSources.size === 0 ? <div className="oa-pending-payment-export-drawer__hint">请至少选择一种 OA 来源。</div> : null}
        {error ? <div className="oa-pending-payments-alert" role="alert">{error}</div> : null}
        {downloadedFileName ? (
          <div className="oa-pending-payments-alert oa-pending-payments-alert--success" role="status">
            已生成 {downloadedFileName}
          </div>
        ) : null}
      </div>
    </AppDrawer>
  );
}

function ExportSourceCheckbox({
  checked,
  indeterminate = false,
  label,
  onChange,
}: {
  checked: boolean;
  indeterminate?: boolean;
  label: string;
  onChange: () => void;
}) {
  return (
    <Checkbox isIndeterminate={indeterminate} isSelected={checked} onChange={onChange}>
      <Checkbox.Control><Checkbox.Indicator /></Checkbox.Control>
      {label}
    </Checkbox>
  );
}

function triggerDownload({ blob, fileName }: OaPendingPaymentExportDownload) {
  if (typeof URL.createObjectURL !== "function") {
    return;
  }
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = fileName;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}
