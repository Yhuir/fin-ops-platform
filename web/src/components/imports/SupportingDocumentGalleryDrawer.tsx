import { Alert, Button, Spinner } from "@heroui/react";
import { ArrowLeft, ExternalLink, FileImage, FileText } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import AppDrawer from "../common/AppDrawer";
import { formatDateTimeText } from "../../features/dateTime";
import {
  listWorkbenchOaSupportingDocumentGallery,
  resolveWorkbenchActionErrorMessage,
} from "../../features/workbench/api";
import type { WorkbenchOaSupportingDocument } from "../../features/workbench/types";

type SupportingDocumentGalleryDrawerProps = {
  open: boolean;
  onClose: () => void;
};

const BUSINESS_TIME_ZONE = "Asia/Shanghai";

function businessDateKey(value: string | Date) {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "unknown";
  const parts = new Intl.DateTimeFormat("en-US", {
    day: "2-digit",
    month: "2-digit",
    timeZone: BUSINESS_TIME_ZONE,
    year: "numeric",
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function dateGroupLabel(key: string) {
  if (key === "unknown") return "上传时间未知";
  const today = businessDateKey(new Date());
  const yesterday = businessDateKey(new Date(Date.now() - 24 * 60 * 60 * 1000));
  if (key === today) return "今天";
  if (key === yesterday) return "昨天";
  const [year, month, day] = key.split("-");
  return `${year}年${Number(month)}月${Number(day)}日`;
}

function formatFileSize(size: number) {
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`;
  if (size >= 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${size} B`;
}

function isAbortError(error: unknown) {
  return error instanceof Error && error.name === "AbortError";
}

export default function SupportingDocumentGalleryDrawer({
  open,
  onClose,
}: SupportingDocumentGalleryDrawerProps) {
  const requestRef = useRef<AbortController | null>(null);
  const [documents, setDocuments] = useState<WorkbenchOaSupportingDocument[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [selected, setSelected] = useState<WorkbenchOaSupportingDocument | null>(null);
  const [failedThumbnails, setFailedThumbnails] = useState<Set<string>>(new Set());

  const loadPage = useCallback(async (cursor = "", replace = false) => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    setLoading(true);
    setErrorMessage(null);
    try {
      const page = await listWorkbenchOaSupportingDocumentGallery({ cursor, signal: controller.signal });
      setDocuments((current) => {
        if (replace) return page.documents;
        const byId = new Map(current.map((document) => [document.id, document]));
        page.documents.forEach((document) => byId.set(document.id, document));
        return Array.from(byId.values());
      });
      setHasMore(page.hasMore);
      setNextCursor(page.nextCursor);
    } catch (error) {
      if (!isAbortError(error)) {
        setErrorMessage(resolveWorkbenchActionErrorMessage(error, "补充凭证加载失败，请稍后重试。"));
      }
    } finally {
      if (requestRef.current === controller) {
        requestRef.current = null;
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    if (!open) {
      requestRef.current?.abort();
      requestRef.current = null;
      setSelected(null);
      return undefined;
    }
    setDocuments([]);
    setHasMore(false);
    setNextCursor(null);
    setFailedThumbnails(new Set());
    void loadPage("", true);
    return () => {
      requestRef.current?.abort();
      requestRef.current = null;
    };
  }, [loadPage, open]);

  const groups = useMemo(() => {
    const grouped = new Map<string, WorkbenchOaSupportingDocument[]>();
    documents.forEach((document) => {
      const key = businessDateKey(document.createdAt);
      grouped.set(key, [...(grouped.get(key) ?? []), document]);
    });
    return Array.from(grouped.entries());
  }, [documents]);

  const title = selected ? "查看补充凭证" : "补充凭证";

  return (
    <AppDrawer
      ariaBusy={loading}
      closeLabel="关闭补充凭证"
      onClose={onClose}
      open={open}
      title={title}
      width="min(960px, 96vw)"
    >
      {selected ? (
        <div className="flex min-h-0 flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Button onPress={() => setSelected(null)} size="sm" type="button" variant="secondary">
              <ArrowLeft aria-hidden="true" size={16} />
              返回全部凭证
            </Button>
            <a
              className="inline-flex items-center gap-1 text-sm font-medium text-primary-600 hover:underline"
              href={selected.contentUrl}
              rel="noopener noreferrer"
              target="_blank"
            >
              新窗口打开
              <ExternalLink aria-hidden="true" size={15} />
            </a>
          </div>
          <div>
            <h3 className="m-0 break-all text-base font-semibold text-default-950">{selected.fileName}</h3>
            <p className="m-0 mt-1 text-xs text-default-500">
              {formatDateTimeText(selected.createdAt)} · {selected.createdBy || "上传人未知"} · {formatFileSize(selected.sizeBytes)}
            </p>
          </div>
          <div className="flex min-h-[28rem] items-center justify-center overflow-hidden border border-default-200 bg-default-50">
            {selected.contentType === "application/pdf" ? (
              <object
                aria-label={`${selected.fileName} PDF 预览`}
                className="h-[70vh] min-h-[28rem] w-full"
                data={selected.contentUrl}
                type="application/pdf"
              >
                <a href={selected.contentUrl} rel="noopener noreferrer" target="_blank">打开 PDF</a>
              </object>
            ) : (
              <img alt={`${selected.fileName} 预览`} className="max-h-[70vh] w-full object-contain" src={selected.contentUrl} />
            )}
          </div>
        </div>
      ) : (
        <div className="space-y-5">
          <p className="m-0 text-sm text-default-600">
            查看关联台上传的全部有效补充凭证。这里仅供查看，不会把文件录入发票池。
          </p>
          {errorMessage ? (
            <Alert role="alert" status="danger">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span>{errorMessage}</span>
                <Button onPress={() => void loadPage("", true)} size="sm" type="button" variant="secondary">重试</Button>
              </div>
            </Alert>
          ) : null}
          {!loading && !errorMessage && documents.length === 0 ? (
            <div className="flex min-h-52 flex-col items-center justify-center gap-2 border border-dashed border-default-300 text-center text-default-500">
              <FileText aria-hidden="true" size={30} />
              <p className="m-0 text-sm">暂无补充凭证</p>
            </div>
          ) : null}
          {groups.map(([key, items]) => (
            <section aria-labelledby={`supporting-document-date-${key}`} key={key}>
              <h3 className="mb-2 mt-0 text-sm font-semibold text-default-800" id={`supporting-document-date-${key}`}>
                {dateGroupLabel(key)}
              </h3>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {items.map((document) => {
                  const thumbnailFailed = failedThumbnails.has(document.id) || !document.thumbnailUrl;
                  const DocumentIcon = document.contentType === "application/pdf" ? FileText : FileImage;
                  return (
                    <button
                      className="overflow-hidden border border-default-200 bg-content1 text-left transition-colors hover:border-primary-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-500"
                      key={document.id}
                      onClick={() => setSelected(document)}
                      type="button"
                    >
                      <span className="flex aspect-[4/3] items-center justify-center bg-default-50">
                        {thumbnailFailed ? (
                          <DocumentIcon aria-hidden="true" className="text-default-400" size={34} />
                        ) : (
                          <img
                            alt={`${document.fileName} 缩略图`}
                            className="h-full w-full object-contain"
                            loading="lazy"
                            onError={() => setFailedThumbnails((current) => new Set(current).add(document.id))}
                            src={document.thumbnailUrl}
                          />
                        )}
                      </span>
                      <span className="block space-y-1 p-3">
                        <span className="block truncate text-sm font-medium text-default-950" title={document.fileName}>{document.fileName}</span>
                        <span className="block text-xs text-default-500">{formatDateTimeText(document.createdAt)} · {formatFileSize(document.sizeBytes)}</span>
                        <span className="block truncate text-xs text-default-500">上传人：{document.createdBy || "未知"}</span>
                        <span className="block truncate text-xs text-default-500" title={`${document.oaRowId} / ${document.expenseItemId}`}>
                          来源：{document.oaRowId} / {document.expenseItemId}
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </section>
          ))}
          {loading ? (
            <div className="flex items-center justify-center gap-2 py-8 text-sm text-default-500">
              <Spinner size="sm" />正在加载补充凭证
            </div>
          ) : null}
          {!loading && !errorMessage && hasMore && nextCursor ? (
            <div className="flex justify-center">
              <Button onPress={() => void loadPage(nextCursor)} size="sm" type="button" variant="secondary">加载更多</Button>
            </div>
          ) : null}
        </div>
      )}
    </AppDrawer>
  );
}
