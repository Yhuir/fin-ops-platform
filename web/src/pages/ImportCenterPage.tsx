import { Button, Chip, Tabs } from "@heroui/react";
import { Car, FileText, Inbox, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  FinanceTable,
  FinanceTableBody,
  FinanceTableCell,
  FinanceTableColumn,
  FinanceTableHeader,
  FinanceTablePagination,
  FinanceTableRow,
  TruncatedCellText,
} from "../components/common/FinanceTable";
import PageScaffold from "../components/common/PageScaffold";
import StatePanel from "../components/common/StatePanel";
import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { fetchImportFactBatches, fetchImportFactFiles } from "../features/imports/api";
import type { ImportBatchType, ImportFactBatch, ImportFactFile } from "../features/imports/types";

const PAGE_SIZE = 50;

const TYPE_LABELS: Record<ImportBatchType, string> = {
  bank_transaction: "银行流水",
  input_invoice: "进项发票",
  output_invoice: "销项发票",
};

const STATUS_LABELS: Record<string, string> = {
  completed: "已完成",
  confirmed: "已确认",
  failed: "失败",
  pending: "待确认",
  preview_ready: "待确认",
  preview_ready_with_errors: "待复核",
  duplicate_file: "重复文件",
  source_control_mismatch: "源文件不一致",
  unrecognized_template: "无法识别",
  skipped: "已跳过",
  reverted: "已撤销",
};

function statusLabel(value: string) {
  return (STATUS_LABELS[value] ?? value) || "—";
}

function statusColor(value: string): "success" | "danger" | "warning" | "default" {
  if (["completed", "confirmed"].includes(value)) return "success";
  if (["failed", "unrecognized_template", "source_control_mismatch"].includes(value)) return "danger";
  if (["pending", "preview_ready", "preview_ready_with_errors", "duplicate_file"].includes(value)) return "warning";
  return "default";
}

function formatTime(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

function typeLabel(value?: ImportBatchType | null) {
  return value ? TYPE_LABELS[value] : "—";
}

function FileRows({ rows }: { rows: ImportFactFile[] }) {
  return (
    <FinanceTable ariaLabel="导入文件记录" minWidth={1080}>
      <FinanceTableHeader>
        <FinanceTableColumn id="file" columnRole="identity" isRowHeader>文件</FinanceTableColumn>
        <FinanceTableColumn id="type" columnRole="status">类型</FinanceTableColumn>
        <FinanceTableColumn id="status" columnRole="status">状态</FinanceTableColumn>
        <FinanceTableColumn id="rows" columnRole="quantity">总行数</FinanceTableColumn>
        <FinanceTableColumn id="success" columnRole="quantity">成功</FinanceTableColumn>
        <FinanceTableColumn id="review" columnRole="quantity">需复核</FinanceTableColumn>
        <FinanceTableColumn id="error" columnRole="quantity">异常</FinanceTableColumn>
        <FinanceTableColumn id="operator" columnRole="identity">操作人</FinanceTableColumn>
        <FinanceTableColumn id="time" columnRole="date">时间</FinanceTableColumn>
        <FinanceTableColumn id="action" columnRole="action">操作</FinanceTableColumn>
      </FinanceTableHeader>
      <FinanceTableBody items={rows}>
        {(row) => (
          <FinanceTableRow id={row.id} textValue={row.fileName}>
            <FinanceTableCell columnRole="identity"><TruncatedCellText value={row.fileName} /></FinanceTableCell>
            <FinanceTableCell columnRole="status">{typeLabel(row.batchType)}</FinanceTableCell>
            <FinanceTableCell columnRole="status">
              <Chip color={statusColor(row.status)} size="sm">{statusLabel(row.status)}</Chip>
            </FinanceTableCell>
            <FinanceTableCell columnRole="quantity">{row.rowCount}</FinanceTableCell>
            <FinanceTableCell columnRole="quantity">{row.successCount}</FinanceTableCell>
            <FinanceTableCell columnRole="quantity">{row.suspectedDuplicateCount + row.duplicateCount}</FinanceTableCell>
            <FinanceTableCell columnRole="quantity">{row.errorCount}</FinanceTableCell>
            <FinanceTableCell columnRole="identity">{row.uploadedBy || "—"}</FinanceTableCell>
            <FinanceTableCell columnRole="date">{formatTime(row.uploadedAt)}</FinanceTableCell>
            <FinanceTableCell columnRole="action">
              {row.previewBatchId && row.errorCount > 0 ? (
                <Button
                  size="sm"
                  variant="tertiary"
                  onPress={() => window.location.assign(`/imports/batches/${row.previewBatchId}/errors.csv`)}
                >
                  下载错误
                </Button>
              ) : "—"}
            </FinanceTableCell>
          </FinanceTableRow>
        )}
      </FinanceTableBody>
    </FinanceTable>
  );
}

function BatchRows({ rows }: { rows: ImportFactBatch[] }) {
  return (
    <FinanceTable ariaLabel="导入批次记录" minWidth={940}>
      <FinanceTableHeader>
        <FinanceTableColumn id="source" columnRole="identity" isRowHeader>来源文件</FinanceTableColumn>
        <FinanceTableColumn id="type" columnRole="status">类型</FinanceTableColumn>
        <FinanceTableColumn id="status" columnRole="status">状态</FinanceTableColumn>
        <FinanceTableColumn id="rows" columnRole="quantity">总行数</FinanceTableColumn>
        <FinanceTableColumn id="success" columnRole="quantity">成功</FinanceTableColumn>
        <FinanceTableColumn id="review" columnRole="quantity">需复核</FinanceTableColumn>
        <FinanceTableColumn id="error" columnRole="quantity">异常</FinanceTableColumn>
        <FinanceTableColumn id="operator" columnRole="identity">操作人</FinanceTableColumn>
        <FinanceTableColumn id="time" columnRole="date">时间</FinanceTableColumn>
      </FinanceTableHeader>
      <FinanceTableBody items={rows}>
        {(row) => (
          <FinanceTableRow id={row.id} textValue={row.sourceName}>
            <FinanceTableCell columnRole="identity"><TruncatedCellText value={row.sourceName} /></FinanceTableCell>
            <FinanceTableCell columnRole="status">{typeLabel(row.batchType)}</FinanceTableCell>
            <FinanceTableCell columnRole="status"><Chip color={statusColor(row.status)} size="sm">{statusLabel(row.status)}</Chip></FinanceTableCell>
            <FinanceTableCell columnRole="quantity">{row.rowCount}</FinanceTableCell>
            <FinanceTableCell columnRole="quantity">{row.successCount}</FinanceTableCell>
            <FinanceTableCell columnRole="quantity">{row.suspectedDuplicateCount + row.duplicateCount}</FinanceTableCell>
            <FinanceTableCell columnRole="quantity">{row.errorCount}</FinanceTableCell>
            <FinanceTableCell columnRole="identity">{row.importedBy || "—"}</FinanceTableCell>
            <FinanceTableCell columnRole="date">{formatTime(row.importedAt)}</FinanceTableCell>
          </FinanceTableRow>
        )}
      </FinanceTableBody>
    </FinanceTable>
  );
}

export default function ImportCenterPage() {
  const navigate = useNavigate();
  const { active, activationGeneration } = useOptionalPageActivation("imports.center");
  const [tab, setTab] = useState<"files" | "batches">("files");
  const [page, setPage] = useState(1);
  const [files, setFiles] = useState<ImportFactFile[]>([]);
  const [batches, setBatches] = useState<ImportFactBatch[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!active) return;
    setLoading(true);
    setError(null);
    try {
      if (tab === "files") {
        const result = await fetchImportFactFiles(page, PAGE_SIZE);
        setFiles(result.items);
        setTotal(result.total);
      } else {
        const result = await fetchImportFactBatches(page, PAGE_SIZE);
        setBatches(result.items);
        setTotal(result.total);
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "导入记录加载失败。");
    } finally {
      setLoading(false);
    }
  }, [active, page, tab]);

  useEffect(() => {
    void load();
  }, [activationGeneration, load]);

  const rowsEmpty = tab === "files" ? files.length === 0 : batches.length === 0;

  return (
    <PageScaffold
      className="import-center-page"
      title="导入中心"
      actions={(
        <Button isPending={loading} variant="secondary" onPress={() => void load()}>
          <RefreshCw aria-hidden="true" size={16} />刷新
        </Button>
      )}
    >
      <div className="import-center-toolbar">
        <Button variant="secondary" onPress={() => navigate("/imports/bank-transactions")}><Inbox aria-hidden="true" size={16} />银行流水导入</Button>
        <Button variant="secondary" onPress={() => navigate("/imports/invoices")}><FileText aria-hidden="true" size={16} />发票导入</Button>
        <Button variant="secondary" onPress={() => navigate("/imports/etc-invoices")}><Car aria-hidden="true" size={16} />ETC发票导入</Button>
      </div>

      <Tabs
        selectedKey={tab}
        onSelectionChange={(key) => {
          setTab(key as "files" | "batches");
          setPage(1);
        }}
      >
        <Tabs.List aria-label="导入记录类型">
          <Tabs.Tab id="files">文件记录</Tabs.Tab>
          <Tabs.Tab id="batches">导入批次</Tabs.Tab>
        </Tabs.List>
      </Tabs>

      {error ? <StatePanel tone="error" title="导入记录加载失败">{error}</StatePanel> : null}
      {!error && loading ? <StatePanel tone="loading" title="正在加载导入记录" /> : null}
      {!error && !loading && rowsEmpty ? <StatePanel tone="empty" title="暂无导入记录" /> : null}
      {!error && !loading && !rowsEmpty ? (tab === "files" ? <FileRows rows={files} /> : <BatchRows rows={batches} />) : null}
      {!error && !loading && total > PAGE_SIZE ? (
        <FinanceTablePagination page={page} pageSize={PAGE_SIZE} total={total} onPageChange={setPage} />
      ) : null}
    </PageScaffold>
  );
}
