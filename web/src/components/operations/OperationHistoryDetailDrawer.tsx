import { Alert, Button, Chip, Spinner } from "@heroui/react";
import { ArrowRight, FileImage, FileText } from "lucide-react";
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

type OperationHistoryDetailDrawerProps = {
  operation: OperationHistoryOperation | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
};

function actorLabel(operation: OperationHistoryOperation) {
  const actorId = String(operation.actor_id ?? "");
  if (!actorId || actorId === "system" || actorId === "database" || actorId.includes("-persistence") || actorId.includes("-repair")) {
    return "系统";
  }
  const name = String(operation.actor_name || "").trim();
  const account = String(operation.actor_account || "").trim();
  return name && account ? `${name} · ${account}` : name || account || actorId;
}

function outcomeView(outcome: string) {
  if (outcome === "success") return { color: "success" as const, label: "成功" };
  if (outcome === "failed") return { color: "danger" as const, label: "失败" };
  if (outcome === "incomplete") return { color: "danger" as const, label: "执行未完成" };
  return { color: "warning" as const, label: "进行中" };
}

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

export default function OperationHistoryDetailDrawer({ operation, loading, error, onClose }: OperationHistoryDetailDrawerProps) {
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
      return undefined;
    }
    const controller = new AbortController();
    let objectUrl: string | null = null;
    setPreviewLoading(true);
    setPreviewError(null);
    void fetchOperationArtifact(selectedArtifact.preview_url, controller.signal)
      .then((blob) => {
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

  const detail = operation?.detail;
  const outcome = outcomeView(operation?.outcome ?? "pending");

  return (
    <AppDrawer ariaBusy={loading} open={operation !== null} title="操作详情" width={720} onClose={onClose}>
      {operation ? (
        <div className="flex flex-col gap-5 pb-6">
          <header className="flex items-start justify-between gap-5 border-b border-default-200 pb-4">
            <div className="min-w-0">
              <p className="m-0 text-xs font-medium text-default-500">具体操作</p>
              <h3 className="mt-1 text-lg font-semibold text-default-950">{operation.action_label}</h3>
              <p className="mt-1 text-sm leading-6 text-default-600">{operation.action_description}</p>
            </div>
            <Chip color={outcome.color} size="sm">{outcome.label}</Chip>
          </header>

          {error ? (
            <Alert role="alert" status="danger">
              <Alert.Indicator />
              <Alert.Content><Alert.Description>{error}</Alert.Description></Alert.Content>
            </Alert>
          ) : null}
          {loading ? <div className="flex items-center gap-2 py-4 text-sm text-default-600"><Spinner size="sm" />正在加载操作证据</div> : null}

          {!loading && !error ? (
            <>
              <dl className="grid grid-cols-1 gap-x-6 sm:grid-cols-2">
                {[
                  ["操作人", actorLabel(operation)],
                  ["页面", pageLabelForKey(operation.page_key)],
                  ["影响对象", operation.object_label || "业务记录"],
                  ["处理结果", outcome.label],
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
                    <h3 className="m-0 text-sm font-semibold text-default-950" id="operation-target-heading">操作对象</h3>
                    <span className="truncate text-xs text-default-500">{detail.target.title}</span>
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
                          <span className="truncate">{change.before || "—"}</span>
                          <ArrowRight aria-hidden="true" className="shrink-0 text-default-400" size={14} />
                          <span className="truncate font-medium">{change.after || "—"}</span>
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
                  <Alert.Content><Alert.Description>这条历史记录产生于详情证据启用之前，未保存可核验的对象快照。</Alert.Description></Alert.Content>
                </Alert>
              ) : null}
            </>
          ) : null}
        </div>
      ) : null}
    </AppDrawer>
  );
}
