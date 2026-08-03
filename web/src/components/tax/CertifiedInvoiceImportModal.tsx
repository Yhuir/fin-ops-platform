import { Alert, Button, Chip, ProgressBar } from "@heroui/react";
import { useEffect, useMemo, useRef, useState } from "react";

import AppDialog from "../common/AppDialog";
import FileDropzone from "../common/FileDropzone";
import {
  EmptyValue,
  FinanceStatusTag,
  FinanceTable,
  FinanceTableBody,
  FinanceTableCell,
  FinanceTableColumn,
  FinanceTableHeader,
  FinanceTableRow,
} from "../common/FinanceTable";
import { useSession } from "../../contexts/SessionContext";
import { formatMoney } from "../../features/money";
import {
  confirmTaxCertifiedImport,
  fetchTaxCertifiedImportJob,
  previewTaxCertifiedImport,
  taxCertifiedImportConfirmedFromJob,
} from "../../features/tax/api";
import type {
  TaxCertifiedImportConfirmedResult,
  TaxCertifiedImportPreviewRow,
  TaxCertifiedImportPreviewResult,
} from "../../features/tax/types";

type CertifiedInvoiceImportModalProps = {
  currentMonth: string;
  onClose: () => void;
  onImported: (result: TaxCertifiedImportConfirmedResult) => Promise<void> | void;
};

function isExcelFile(file: File) {
  const normalizedName = file.name.toLowerCase();
  return normalizedName.endsWith(".xls") || normalizedName.endsWith(".xlsx");
}

function rowStatusLabel(row: TaxCertifiedImportPreviewRow) {
  if (row.rowStatus === "invalid") {
    return "无效";
  }
  if (row.matchStatus === "matched_plan") {
    return "匹配计划";
  }
  if (row.matchStatus === "outside_plan") {
    return "未进入计划";
  }
  return "待确认";
}

function dedupeStatusLabel(row: TaxCertifiedImportPreviewRow) {
  if (row.dedupeStatus === "duplicate") {
    return "重复";
  }
  if (row.dedupeStatus === "new") {
    return "新记录";
  }
  return "--";
}

function rowStatusTone(row: TaxCertifiedImportPreviewRow) {
  if (row.rowStatus === "invalid") {
    return "danger";
  }
  if (row.matchStatus === "matched_plan") {
    return "success";
  }
  if (row.matchStatus === "outside_plan") {
    return "warning";
  }
  return "neutral";
}

function Notice({
  status,
  children,
}: {
  status: "accent" | "danger" | "success" | "warning";
  children: string;
}) {
  return (
    <Alert role={status === "danger" ? "alert" : "status"} status={status}>
      <Alert.Indicator />
      <Alert.Content>
        <Alert.Description>{children}</Alert.Description>
      </Alert.Content>
    </Alert>
  );
}

function InlineProgress({ label }: { label: string }) {
  return (
    <div className="certified-import-progress" role="status">
      <p>{label}</p>
      <ProgressBar aria-label={label} color="accent" isIndeterminate size="sm">
        <ProgressBar.Track>
          <ProgressBar.Fill />
        </ProgressBar.Track>
      </ProgressBar>
    </div>
  );
}

export default function CertifiedInvoiceImportModal({
  currentMonth,
  onClose,
  onImported,
}: CertifiedInvoiceImportModalProps) {
  const session = useSession();
  const isMountedRef = useRef(false);
  const canMutateData =
    session.status === "authenticated" ? session.session.canMutateData : false;
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [previewResult, setPreviewResult] = useState<TaxCertifiedImportPreviewResult | null>(null);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [confirmMessage, setConfirmMessage] = useState("正在导入已认证结果并刷新税金抵扣页面...");

  const canPreview = canMutateData && selectedFiles.length > 0 && !isPreviewing && !isConfirming;
  const canConfirm = canMutateData && previewResult !== null && !isPreviewing && !isConfirming;
  const importedBy =
    session.status === "authenticated" || session.status === "forbidden"
      ? session.session.user.username || session.session.user.displayName || "system"
      : "system";

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const fileHint = useMemo(() => {
    if (selectedFiles.length === 0) {
      return "支持一次选择多个 Excel 文件，先预览识别结果，再确认导入并刷新本页。";
    }
    return `已选择 ${selectedFiles.length} 个文件，当前页面月份为 ${currentMonth}。确认导入后会刷新当前税金抵扣页。`;
  }, [currentMonth, selectedFiles.length]);

  function updateSelectedFiles(files: File[]) {
    setSelectedFiles(files);
    setPreviewResult(null);
    setErrorMessage(null);
  }

  function applyDroppedFiles(files: File[]) {
    const validFiles = files.filter(isExcelFile);
    const invalidFiles = files.filter((file) => !isExcelFile(file));
    if (validFiles.length > 0) {
      updateSelectedFiles(validFiles);
    }
    if (invalidFiles.length > 0) {
      if (validFiles.length === 0) {
        setPreviewResult(null);
      }
      setErrorMessage("仅支持 .xls/.xlsx");
    }
  }

  async function handlePreview() {
    if (selectedFiles.length === 0) {
      setErrorMessage("请先选择至少一个已认证发票 Excel 文件。");
      return;
    }
    setErrorMessage(null);
    setIsPreviewing(true);
    try {
      const result = await previewTaxCertifiedImport({
        importedBy,
        files: selectedFiles,
      });
      setPreviewResult(result);
    } catch {
      setErrorMessage("已认证发票预览失败，请稍后重试。");
    } finally {
      setIsPreviewing(false);
    }
  }

  async function handleConfirm() {
    if (!previewResult) {
      setErrorMessage("请先预览识别结果，再确认导入。");
      return;
    }
    setErrorMessage(null);
    setConfirmMessage("正在导入已认证结果并刷新税金抵扣页面...");
    setIsConfirming(true);
    try {
      const result = await confirmTaxCertifiedImport(previewResult.sessionId);
      if (result.status === "queued") {
        setConfirmMessage("已提交导入任务，正在等待后台确认结果...");
        await new Promise((resolve) => {
          window.setTimeout(resolve, 250);
        });
        for (let attempt = 0; attempt < 120; attempt += 1) {
          const job = await fetchTaxCertifiedImportJob(result.importJob.importJobId);
          const normalizedStatus = job.status.toLowerCase();
          const normalizedStage = job.stage.toLowerCase();
          if (normalizedStatus === "succeeded" || normalizedStage === "succeeded" || normalizedStage === "completed") {
            const confirmedResult = taxCertifiedImportConfirmedFromJob(job);
            if (!confirmedResult) {
              throw new Error("Tax certified import job succeeded without a batch result.");
            }
            if (!isMountedRef.current) {
              return;
            }
            await onImported(confirmedResult);
            return;
          }
          if (normalizedStatus === "failed" || normalizedStage === "failed") {
            throw new Error(job.lastError || "Tax certified import job failed.");
          }
          await new Promise((resolve) => {
            window.setTimeout(resolve, 1000);
          });
          if (!isMountedRef.current) {
            return;
          }
        }
        throw new Error("Tax certified import job polling timed out.");
      }
      if (!isMountedRef.current) {
        return;
      }
      await onImported(result);
    } catch (error) {
      if (!isMountedRef.current) {
        return;
      }
      setErrorMessage(error instanceof Error && error.message
        ? error.message
        : "已认证发票导入失败，请稍后重试。");
      setIsConfirming(false);
    }
  }

  return (
    <AppDialog
      disableEscapeClose={isConfirming}
      maxWidth="md"
      open
      title="已认证发票导入"
      description="在税金抵扣页内完成已认证发票预览、确认导入和页面刷新，不跳转到关联台导入界面。"
      onClose={() => {
        if (!isConfirming) {
          onClose();
        }
      }}
      actions={(
        <>
          <Button isDisabled={isConfirming} type="button" variant="tertiary" onPress={onClose}>
            取消
          </Button>
          <Button isDisabled={!canPreview} type="button" variant="outline" onPress={handlePreview}>
            预览识别结果
          </Button>
          <Button isDisabled={!canConfirm} isPending={isConfirming} type="button" onPress={handleConfirm}>
            确认导入
          </Button>
        </>
      )}
    >
      <div className="certified-import-body">
        <FileDropzone
          accept=".xlsx,.xls"
          disabled={!canMutateData || isPreviewing || isConfirming}
          errorText={errorMessage}
          helperText={fileHint}
          label="选择已认证发票文件"
          multiple
          onFiles={applyDroppedFiles}
        />

        {!canMutateData ? (
          <Notice status="accent">当前账号仅支持查看和导出，不能导入已认证发票。</Notice>
        ) : null}

        {selectedFiles.length > 0 ? (
          <section className="certified-import-file-list" aria-label="已选择文件">
            {selectedFiles.map((file) => (
              <div key={`${file.name}-${file.lastModified}-${file.size}`} className="certified-import-file-item">
                <strong>{file.name}</strong>
                <span>{(file.size / 1024).toFixed(1)} KB</span>
              </div>
            ))}
          </section>
        ) : (
          <Notice status="accent">当前还没有选择文件。</Notice>
        )}

        {isPreviewing ? <InlineProgress label="正在识别已认证发票，请稍候..." /> : null}
        {isConfirming ? <InlineProgress label={confirmMessage} /> : null}

        {previewResult ? (
          <section className="export-center-preview" aria-label="已认证发票预览结果">
            <div className="export-center-preview-header">
              <h3>预览结果</h3>
              <Chip size="sm" variant="secondary">{previewResult.fileCount} 个文件</Chip>
            </div>
            <div className="export-center-preview-body">
              <div className="export-center-preview-summary certified-import-summary">
                <Chip color="accent" variant="soft">识别记录 {previewResult.summary.recognizedCount} 条</Chip>
                <Chip variant="secondary">匹配计划 {previewResult.summary.matchedPlanCount} 条</Chip>
                <Chip variant="secondary">未进入计划 {previewResult.summary.outsidePlanCount} 条</Chip>
                <Chip variant="secondary">无效记录 {previewResult.summary.invalidCount} 条</Chip>
              </div>
              <div className="certified-import-preview-files">
                {previewResult.files.map((file) => (
                  <section key={file.id} className="certified-import-preview-file">
                    <div className="certified-import-preview-file-header">
                      <strong>{file.fileName}</strong>
                      <Chip size="sm" variant="secondary">{file.month}</Chip>
                    </div>
                    <div className="certified-import-preview-file-meta">
                      <span>识别 {file.recognizedCount} 条</span>
                      <span>匹配计划 {file.matchedPlanCount} 条</span>
                      <span>未进入计划 {file.outsidePlanCount} 条</span>
                      <span>无效 {file.invalidCount} 条</span>
                    </div>
                    {file.rows.length > 0 ? (
                      <FinanceTable ariaLabel={`${file.fileName} 行级预览结果`} className="certified-import-preview-row-table" minWidth={760}>
                        <FinanceTableHeader>
                          <FinanceTableColumn columnRole="quantity">行号</FinanceTableColumn>
                          <FinanceTableColumn columnRole="identity" isRowHeader>发票号码</FinanceTableColumn>
                          <FinanceTableColumn columnRole="account">销方</FinanceTableColumn>
                          <FinanceTableColumn columnRole="amount">税额</FinanceTableColumn>
                          <FinanceTableColumn columnRole="status">状态</FinanceTableColumn>
                          <FinanceTableColumn columnRole="status">重复</FinanceTableColumn>
                          <FinanceTableColumn columnRole="description">原因</FinanceTableColumn>
                        </FinanceTableHeader>
                        <FinanceTableBody>
                          {file.rows.map((row) => {
                            const invoiceNo = row.digitalInvoiceNo || row.invoiceNo || "";
                            const sellerName = row.sellerName || "";
                            const taxAmount = row.deductibleTaxAmount || row.taxAmount || "";
                            const errorMessageText = row.errorMessage || "";

                            return (
                              <FinanceTableRow
                                key={`${file.id}-${row.sourceRowNumber}-${row.id}`}
                                id={`${file.id}-${row.sourceRowNumber}-${row.id}`}
                                textValue={`${invoiceNo} ${sellerName} ${rowStatusLabel(row)} ${dedupeStatusLabel(row)}`}
                              >
                                <FinanceTableCell columnRole="quantity" textValue={String(row.sourceRowNumber)}>
                                  {row.sourceRowNumber}
                                </FinanceTableCell>
                                <FinanceTableCell columnRole="identity" textValue={invoiceNo}>
                                  {invoiceNo || <EmptyValue />}
                                </FinanceTableCell>
                                <FinanceTableCell columnRole="account" textValue={sellerName}>
                                  {sellerName || <EmptyValue />}
                                </FinanceTableCell>
                                <FinanceTableCell columnRole="amount" textValue={formatMoney(taxAmount, "-")}>
                                  {taxAmount ? formatMoney(taxAmount) : <EmptyValue />}
                                </FinanceTableCell>
                                <FinanceTableCell columnRole="status" textValue={rowStatusLabel(row)}>
                                  <FinanceStatusTag tone={rowStatusTone(row)}>{rowStatusLabel(row)}</FinanceStatusTag>
                                </FinanceTableCell>
                                <FinanceTableCell columnRole="status" textValue={dedupeStatusLabel(row)}>
                                  {dedupeStatusLabel(row)}
                                </FinanceTableCell>
                                <FinanceTableCell columnRole="description" textValue={errorMessageText}>
                                  {errorMessageText || <EmptyValue />}
                                </FinanceTableCell>
                              </FinanceTableRow>
                            );
                          })}
                        </FinanceTableBody>
                      </FinanceTable>
                    ) : null}
                  </section>
                ))}
              </div>
            </div>
          </section>
        ) : null}
      </div>
    </AppDialog>
  );
}
