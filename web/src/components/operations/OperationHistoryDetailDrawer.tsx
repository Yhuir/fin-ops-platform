import { Alert, Button, Chip, Spinner } from "@heroui/react";
import { ArrowRight, Copy, FileImage, FileText } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { pageLabelForKey } from "../../app/pageRegistry";
import { formatDateTimeText } from "../../features/dateTime";
import {
  fetchOperationArtifact,
  type OperationHistoryArtifact,
  type OperationHistoryField,
  type OperationHistoryOperation,
} from "../../features/operationHistory/api";
import AppDrawer from "../common/AppDrawer";
import { actorLabel, outcomeView } from "../../features/operationHistory/presentation";

type OperationHistoryDetailDrawerProps = {
  operation: OperationHistoryOperation | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
  onRetry: () => void;
};

function fieldList(fields: OperationHistoryField[]) {
  return (
    <dl className="grid grid-cols-1 gap-x-6 sm:grid-cols-2">
      {fields.map((field) => (
        <div className="grid min-w-0 grid-cols-[6rem_minmax(0,1fr)] gap-3 border-b border-default-200 py-2 text-sm" key={`${field.label}-${field.value}`}>
          <dt className="text-default-500">{field.label}</dt>
          <dd className="m-0 break-words text-default-900">{field.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function formatFileSize(value?: number | null) {
  const bytes = Number(value ?? 0);
  if (!Number.isFinite(bytes) || bytes <= 0) return "大小未知";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function availabilityLabel(artifact: OperationHistoryArtifact) {
  if (artifact.availability === "available") return "可预览";
  if (artifact.availability === "deleted") return "已删除";
  return "未保存";
}

export default function OperationHistoryDetailDrawer({ operation, loading, error, onClose, onRetry }: OperationHistoryDetailDrawerProps) {
  const availableArtifacts = useMemo(
    () => operation?.detail?.artifacts.filter((artifact) => artifact.availability === "available" && artifact.preview_url) ?? [],
    [operation],
  );
  const [selectedArtifactKey, setSelectedArtifactKey] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const selectedArtifact = availableArtifacts.find((artifact) => artifact.artifact_key === selectedArtifactKey) ?? null;

  useEffect(() => {
    setSelectedArtifactKey(availableArtifacts[0]?.artifact_key ?? null);
  }, [operation?.operation_key, availableArtifacts]);

  useEffect(() => {
    if (!selectedArtifact?.preview_url) {
      setPreviewUrl(null);
      setPreviewError(null);
      setPreviewLoading(false);
      return undefined;
    }
    const controller = new AbortController();
    let objectUrl: string | null = null;
    setPreviewLoading(true);
    setPreviewUrl(null);
    setPreviewError(null);
    void fetchOperationArtifact(selectedArtifact.preview_url, controller.signal)
      .then((blob) => {
        if (controller.signal.aborted) return;
        objectUrl = URL.createObjectURL(blob);
        setPreviewUrl(objectUrl);
      })
      .catch((previewLoadError) => {
        if (!controller.signal.aborted) {
          setPreviewError(previewLoadError instanceof Error ? previewLoadError.message : "凭证预览加载失败。");
          setPreviewUrl(null);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setPreviewLoading(false);
      });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [selectedArtifact]);

  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);
  useEffect(() => setCopyFeedback(null), [operation?.operation_key]);
  const copyCall = async (text: string) => {
    try { await navigator.clipboard.writeText(text); setCopyFeedback("API 调用信息已复制"); }
    catch { setCopyFeedback("复制失败，请手动复制"); }
  };
  const detail = operation?.detail;
  const outcome = outcomeView(operation?.outcome ?? "pending");

  return (
    <AppDrawer ariaBusy={loading} open={operation !== null} title="操作详情" width={800} className="operation-history-drawer" onClose={onClose}>
      {operation ? (
        <div className="flex flex-col gap-5 pb-6">
          <header className="flex items-start justify-between gap-5 border-b border-default-200 pb-4">
            <div className="min-w-0">
              <h3 className="m-0 text-lg font-semibold text-default-950">{operation.action_label}</h3>
            </div>
            <Chip color={outcome.color} size="sm">{outcome.label}</Chip>
          </header>

          {error ? (
            <Alert role="alert" status="danger">
              <Alert.Indicator />
              <Alert.Content><Alert.Description>{error}</Alert.Description><Button size="sm" variant="secondary" onPress={onRetry}>重试详情</Button></Alert.Content>
            </Alert>
          ) : null}
          {loading ? <div className="flex items-center gap-2 py-4 text-sm text-default-600"><Spinner size="sm" />正在加载操作证据</div> : null}

          {!loading && !error ? (
            <>
              <dl className="grid grid-cols-1 gap-x-6 sm:grid-cols-2">
                {[
                  ["操作人", actorLabel(operation)],
                  ["页面", pageLabelForKey(operation.page_key)],
                  ["分类", operation.category_label],
                  ["来源", detail?.source],
                  ["开始时间", formatDateTimeText(operation.started_at)],
                  ["完成时间", formatDateTimeText(operation.completed_at)],
                ].map(([label, value]) => (
                  <div className="grid grid-cols-[5rem_minmax(0,1fr)] gap-3 border-b border-default-200 py-2 text-sm" key={label}>
                    <dt className="text-default-500">{label}</dt>
                    <dd className="m-0 break-words text-default-900">{value}</dd>
                  </div>
                ))}
              </dl>

              {detail?.failure ? (
                <Alert role="alert" status="danger">
                  <Alert.Indicator />
                  <Alert.Content>
                    <Alert.Title>操作未完成</Alert.Title>
                    <Alert.Description>{detail.failure.message}</Alert.Description>
                  </Alert.Content>
                </Alert>
              ) : null}

              {detail?.target ? (
                <section aria-labelledby="operation-target-heading" className="border-t border-default-300 pt-4">
                  <div className="mb-2 flex items-baseline justify-between gap-3">
                    <h3 className="m-0 text-sm font-semibold text-default-950" id="operation-target-heading">实际影响</h3>
                    <span className="break-words text-xs text-default-500">{detail.target.title}</span>
                  </div>
                  {fieldList(detail.target.fields)}
                </section>
              ) : null}

              {detail?.changes.length ? (
                <section aria-labelledby="operation-change-heading" className="border-t border-default-300 pt-4">
                  <h3 className="mb-2 text-sm font-semibold text-default-950" id="operation-change-heading">结果变化</h3>
                  <div className="divide-y divide-default-200 border-y border-default-200">
                    {detail.changes.map((change) => (
                      <div className="grid grid-cols-[6rem_minmax(0,1fr)] items-center gap-3 py-2 text-sm" key={`${change.label}-${change.before}-${change.after}`}>
                        <span className="text-default-500">{change.label}</span>
                        <span className="flex min-w-0 items-center gap-2 text-default-900">
                          <span className="break-words">{change.before || "—"}</span>
                          <ArrowRight aria-hidden="true" className="shrink-0 text-default-400" size={14} />
                          <span className="break-words font-medium">{change.after || "—"}</span>
                        </span>
                      </div>
                    ))}
                  </div>
                </section>
              ) : null}

              {detail?.artifacts.length ? (
                <section aria-labelledby="operation-artifacts-heading" className="border-t border-default-300 pt-4">
                  <h3 className="mb-2 text-sm font-semibold text-default-950" id="operation-artifacts-heading">相关文件</h3>
                  <div className="divide-y divide-default-200 border-y border-default-200">
                    {detail.artifacts.map((artifact) => {
                      const Icon = artifact.media_type === "application/pdf" ? FileText : FileImage;
                      const canPreview = artifact.availability === "available" && Boolean(artifact.preview_url);
                      return (
                        <div className="flex min-w-0 items-center gap-3 py-2" key={artifact.artifact_key}>
                          <Icon aria-hidden="true" className="shrink-0 text-default-500" size={18} />
                          <div className="min-w-0 flex-1">
                            <p className="m-0 truncate text-sm font-medium text-default-900">{artifact.title}</p>
                            <p className="m-0 text-xs text-default-500">{formatFileSize(artifact.size_bytes)} · {availabilityLabel(artifact)}</p>
                          </div>
                          {canPreview ? (
                            <Button size="sm" variant={selectedArtifact?.artifact_key === artifact.artifact_key ? "secondary" : "tertiary"} onPress={() => setSelectedArtifactKey(artifact.artifact_key)}>
                              预览
                            </Button>
                          ) : null}
                        </div>
                      );
                    })}
                  </div>
                  {previewLoading ? <div className="flex h-52 items-center justify-center gap-2 text-sm text-default-500"><Spinner size="sm" />正在加载预览</div> : null}
                  {previewError ? <Alert className="mt-3" role="alert" status="danger">{previewError}</Alert> : null}
                  {previewUrl && selectedArtifact ? (
                    <div className="mt-3 overflow-hidden border border-default-200 bg-default-50">
                      {selectedArtifact.media_type === "application/pdf" ? (
                        <object aria-label={`${selectedArtifact.title} PDF 预览`} className="h-[30rem] w-full" data={previewUrl} type="application/pdf" />
                      ) : (
                        <img alt={`${selectedArtifact.title} 预览`} className="max-h-[30rem] w-full object-contain" src={previewUrl} />
                      )}
                    </div>
                  ) : null}
                </section>
              ) : null}

              {detail?.records.length ? (
                <section aria-labelledby="operation-records-heading" className="border-t border-default-300 pt-4">
                  <h3 className="mb-2 text-sm font-semibold text-default-950" id="operation-records-heading">涉及记录</h3>
                  <div className="divide-y divide-default-300 border-y border-default-300">
                    {detail.records.map((record) => (
                      <div className="py-3" key={record.record_key}>
                        <div className="mb-1 flex items-center gap-2">
                          <Chip color="default" size="sm">{record.kind === "invoice" ? "发票" : "记录"}</Chip>
                          <h4 className="m-0 min-w-0 truncate text-sm font-medium text-default-950">{record.title}</h4>
                        </div>
                        {fieldList(record.fields)}
                      </div>
                    ))}
                  </div>
                </section>
              ) : null}

              {detail?.legacy_evidence_missing ? (
                <Alert status="default">
                  <Alert.Indicator />
                  <Alert.Content><Alert.Description>未保存可核验的对象快照。</Alert.Description></Alert.Content>
                </Alert>
              ) : null}

              <section aria-labelledby="operation-api-heading" className="operation-api-section">
                <h3 id="operation-api-heading">API 调用</h3>
                {detail?.api_calls.length ? detail.api_calls.map((call, index) => (
                  <div className="operation-api-call" key={`${call.request_id}-${index}`}>
                    <div className="operation-api-call__heading">
                      <span className="operation-api-method">{call.method ?? "方法未记录"}</span>
                      <code>{call.path ?? "路径未记录"}</code>
                      <Button aria-label="复制 API 调用信息" size="sm" variant="tertiary" isIconOnly onPress={() => void copyCall(`${call.method ?? "方法未记录"} ${call.path ?? "路径未记录"}\n请求 ID：${call.request_id ?? "未记录"}`)}><Copy size={16} aria-hidden="true" /></Button>
                    </div>
                    {fieldList([
                      { label: "HTTP 状态", value: call.status_code === null ? "未记录" : String(call.status_code) },
                      { label: "请求耗时", value: call.duration_ms === null ? "未记录" : `${call.duration_ms} ms` },
                      { label: "请求 ID", value: call.request_id ?? "未记录" },
                    ])}
                    {call.parameters.length ? <div className="operation-api-parameters"><h4>请求参数</h4>{fieldList(call.parameters)}</div> : null}
                  </div>
                )) : <p className="operation-history-missing">未记录 API 调用信息。</p>}
                {copyFeedback ? <p role="status" className="operation-copy-feedback">{copyFeedback}</p> : null}
              </section>
              {detail?.activities.length ? (
                <section aria-labelledby="operation-activities-heading" className="operation-activities">
                  <h3 id="operation-activities-heading">后续处理</h3>
                  {detail.activities.map((activity, index) => {
                    const phase = outcomeView(activity.outcome);
                    return <div className="operation-activity" key={`${activity.occurred_at}-${index}`}>
                      <div className="operation-activity__heading"><strong>{activity.title}</strong><Chip size="sm" color={phase.color}>{phase.label}</Chip></div>
                      <time>{formatDateTimeText(activity.occurred_at)}</time>
                      {fieldList(activity.fields)}
                    </div>;
                  })}
                </section>
              ) : null}


            </>
          ) : null}
        </div>
      ) : null}
    </AppDrawer>
  );
}
